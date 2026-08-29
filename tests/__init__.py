"""Test package.

This file is what makes ``from .conftest import ...`` work in the test modules.
Without it pytest treats ``tests/`` as a plain directory, the relative import
has no parent package, and every module fails to import.

It also has a useful side effect: pytest walks up past this package and puts
the repository root on ``sys.path``, so ``import colophon`` resolves without
installing the project.
"""
