
"""
Errors
"""

__all__ = [
    'FileIndexException',
    'EntanglementIndexException',
    'NoEntangledWorkspaceError',
]

class FileIndexException(Exception):
    pass

class EntanglementIndexException(Exception):
    pass

class NoEntangledWorkspaceError(Exception):
    pass
