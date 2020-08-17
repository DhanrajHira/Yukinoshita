import abc

class NetworkBase(abc.ABC):
    @abc.abstractmethod
    def get(self):
        pass