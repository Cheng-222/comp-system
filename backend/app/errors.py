class APIError(Exception):
    def __init__(self, message, status=400, code=None, data=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code or status
        self.data = data or {}
