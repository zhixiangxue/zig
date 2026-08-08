from __future__ import annotations


class ZigError(Exception):
    pass


class InvalidGraphURIError(ZigError, ValueError):
    pass


class UnsupportedBackendError(ZigError, ValueError):
    pass


class UnsupportedCapabilityError(ZigError):
    pass


class UnsupportedQueryLanguageError(ZigError, ValueError):
    pass


class GraphOperationError(ZigError):
    pass


class NLQError(ZigError):
    pass


class NLQConfigurationError(NLQError):
    pass


class NLQValidationError(NLQError):
    pass
