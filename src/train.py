"""
Code to train a neural network to identify whether a given word image is struck through or not.
"""
import logging
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import torch
from sklearn.metrics import f1_score, accuracy_score
from torch.utils.data import DataLoader

from configuration import Configuration, getConfiguration
from dataset import CleanStruckDataset
from utils import composeTransformations, getModelByName

INFO_LOGGER_NAME = "st_identification"
TRAIN_LOGGER_NAME = "train"
VALIDATION_LOGGER_NAME = "validation"


def initLogger(config: Configuration, auxiliaryLoggerNames: List[str] = None) -> None:
    """
    Utility function initialising a default info logger, as well as one logger per name provided in
    auxiliaryLoggerNames.

    Parameters
    ----------
    config : Configuration
        experiment configuration, to obtain the output location for file loggers
    auxiliaryLoggerNames : List[str]
        additional loggers will be initialised for each name given in this list

    Returns
    -------
        None
    """
    if not auxiliaryLoggerNames:
        auxiliaryLoggerNames = [TRAIN_LOGGER_NAME, VALIDATION_LOGGER_NAME]
    _logger = logging.getLogger(INFO_LOGGER_NAME)
    _logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(message)s', '%d-%b-%y %H:%M:%S')

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.DEBUG)
    consoleHandler.setFormatter(formatter)
    _logger.addHandler(consoleHandler)

    fileHandler = logging.FileHandler(config.outDir / "info.log")
    fileHandler.setLevel(logging.INFO)
    fileHandler.setFormatter(formatter)
    _logger.addHandler(fileHandler)

    for lo in auxiliaryLoggerNames:
        _logger = logging.getLogger(lo)
        _logger.setLevel(logging.INFO)
        fileHandler = logging.FileHandler(config.outDir / "{}.log".format(lo))
        fileHandler.setLevel(logging.INFO)
        _logger.addHandler(fileHandler)


class TrainRunner:
    """
    Utility class that wraps the initialisation, training and validation steps of the training run.
    """

    def __init__(self, config: Configuration, logger: logging.Logger):
        self.config = config
        self.logger = logger

        transformations = composeTransformations(self.config)

        trainDataSet = CleanStruckDataset(self.config.trainImageDir, transforms=transformations,
                                          count=self.config.count)
        validationDataSet = CleanStruckDataset(self.config.testImageDir, transforms=transformations)

        self.trainDataLoader = DataLoader(trainDataSet, batch_size=self.config.batchSize, shuffle=True, num_workers=1)
        self.validationDataLoader = DataLoader(validationDataSet, batch_size=self.config.batchSize, shuffle=False,
                                               num_workers=1)

        self.model = getModelByName(self.config.modelName)

        self.model = self.model.to(self.config.device)

        self.lossFunction = torch.nn.CrossEntropyLoss()

        self.optimiser = torch.optim.Adam(self.model.parameters(), lr=self.config.learningRate, betas=self.config.betas)

    def train(self) -> None:
        self.logger.info(self.config.device)
        trainLogger = logging.getLogger(TRAIN_LOGGER_NAME)
        trainLogger.info("epoch,loss")
        validationLogger = logging.getLogger(VALIDATION_LOGGER_NAME)
        validationLogger.info("epoch,f1,accuracy")
        bestF1 = float('-inf')


        for epoch in range(1, self.config.epochs + 1):
            epochStartTime = time.time()
            
            trainLoss = self.trainOneEpoch()
            trainLogger.info("%d,%f", epoch, trainLoss)
            run_time = time.time() - epochStartTime
            self.logger.info('[%d/%d], loss: %f, time:%f', epoch, self.config.epochs, trainLoss, run_time)
            
            if epoch > 1 and self.config.modelSaveEpoch > 0 and epoch % self.config.modelSaveEpoch == 0:
                torch.save(self.model.state_dict(), self.config.outDir / Path('epoch_{}.pth'.format(epoch)))
                self.logger.info('Epoch %d: model saved', epoch)

            if self.config.validationEpoch > 0 and epoch % self.config.validationEpoch == 0:
                f1, acc = self.validateOneEpoch()
                self.logger.info("Epoch %d -- f1: %f, acc: %s", epoch, f1, acc)
                if f1 > bestF1:
                    bestF1 = f1
                    torch.save({'epoch': epoch, 'model_state_dict': self.model.state_dict(), },
                               self.config.outDir / 'best_f1.pth')
                    self.logger.info('%d: Updated best model', epoch)

                validationLogger.info("%d,%f,%f", epoch, f1, acc)

    def trainOneEpoch(self) -> float:
        """
        Trains the neural network for one epoch.

        Returns
        -------
            mean loss over all batches in this epoch
        """
        
        self.model.train()
        recLosses = []
        for datapoints in self.trainDataLoader:
            self.optimiser.zero_grad()
            image = datapoints["image"].to(self.config.device)
            expectedLabel = datapoints["label"].to(self.config.device)
            predicted = self.model(image)
            predicted = torch.nn.functional.softmax(predicted, dim=1)
            recLoss = self.lossFunction(predicted, expectedLabel)
            recLoss.backward()
            self.optimiser.step()
            recLosses.append(recLoss.item())
        return np.mean(recLosses).item()

    def validateOneEpoch(self) -> Tuple[float, float]:
        """
        Validates the neural network at the current training stage.

        Returns
        -------
        Tuple[float, float]
            f1 and accuracy scores of the validation set
        """
        self.model.eval()
        predictedLabels = []
        expectedLabels = []

        with torch.no_grad():
            for datapoints in self.validationDataLoader:
                image = datapoints["image"].to(self.config.device)
                expectedLabel = datapoints["label"].to(self.config.device)
                predicted = self.model(image)
                predicted = torch.nn.functional.softmax(predicted, dim=1)

                expectedLabels.extend(expectedLabel.cpu().numpy().tolist())
                predictedLabels.extend(torch.max(predicted, dim=1).indices.cpu().numpy().tolist())

        return f1_score(expectedLabels, predictedLabels), accuracy_score(expectedLabels, predictedLabels)


if __name__ == "__main__":
    conf = getConfiguration()
    initLogger(conf)
    logger = logging.getLogger(INFO_LOGGER_NAME)
    logger.info(conf.fileSection)
    runner = TrainRunner(conf, logger)
    logger.info("Start training ...")
    runner.train()
