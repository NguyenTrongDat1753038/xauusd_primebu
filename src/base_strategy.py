class BaseStrategy:
    def __init__(self, params):
        self.params = params

    def get_signal(self, data):
        raise NotImplementedError("This method should be implemented by subclasses.")