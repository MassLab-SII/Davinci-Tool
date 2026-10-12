"""
Dependency Analyzer for Python Scripts
========================================

Analyzes Python verification scripts to detect third-party dependencies
and generate pip install commands for Docker images.
"""

import ast
import logging
import sys
from typing import List, Set, Dict

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Analyzes Python scripts to extract third-party package dependencies."""
    
    # Mapping from import names to pip package names
    # This handles cases where the import name differs from the package name
    IMPORT_TO_PACKAGE = {
        'PIL': 'pillow',
        'cv2': 'opencv-python',
        'sklearn': 'scikit-learn',
        'yaml': 'pyyaml',
        'dotenv': 'python-dotenv',
        'bs4': 'beautifulsoup4',
        'Image': 'pillow',
        'ImageDraw': 'pillow',
        'ImageFont': 'pillow',
    }
    
    def __init__(self):
        """Initialize the dependency analyzer."""
        # Get list of standard library modules for current Python version
        self.stdlib_modules = self._get_stdlib_modules()
        
    def _get_stdlib_modules(self) -> Set[str]:
        """Get set of standard library module names.
        
        Returns:
            Set of standard library module names
        """
        # Common standard library modules (Python 3.x)
        # This is a comprehensive list but not exhaustive
        stdlib = {
            'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio',
            'asyncore', 'atexit', 'audioop', 'base64', 'bdb', 'binascii',
            'binhex', 'bisect', 'builtins', 'bz2', 'calendar', 'cgi', 'cgitb',
            'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop', 'collections',
            'colorsys', 'compileall', 'concurrent', 'configparser', 'contextlib',
            'contextvars', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv', 'ctypes',
            'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib',
            'dis', 'distutils', 'doctest', 'email', 'encodings', 'enum', 'errno',
            'faulthandler', 'fcntl', 'filecmp', 'fileinput', 'fnmatch', 'formatter',
            'fractions', 'ftplib', 'functools', 'gc', 'getopt', 'getpass', 'gettext',
            'glob', 'graphlib', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html',
            'http', 'idlelib', 'imaplib', 'imghdr', 'imp', 'importlib', 'inspect',
            'io', 'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3', 'linecache',
            'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal', 'math',
            'mimetypes', 'mmap', 'modulefinder', 'msilib', 'msvcrt', 'multiprocessing',
            'netrc', 'nis', 'nntplib', 'numbers', 'operator', 'optparse', 'os',
            'ossaudiodev', 'parser', 'pathlib', 'pdb', 'pickle', 'pickletools',
            'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix',
            'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile',
            'pyclbr', 'pydoc', 'queue', 'quopri', 'random', 're', 'readline',
            'reprlib', 'resource', 'rlcompleter', 'runpy', 'sched', 'secrets',
            'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal', 'site',
            'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3',
            'ssl', 'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess',
            'sunau', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile',
            'telnetlib', 'tempfile', 'termios', 'test', 'textwrap', 'threading',
            'time', 'timeit', 'tkinter', 'token', 'tokenize', 'tomllib', 'trace',
            'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types',
            'typing', 'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv',
            'warnings', 'wave', 'weakref', 'webbrowser', 'winreg', 'winsound',
            'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport',
            'zlib', '_thread'
        }
        
        return stdlib
    
    def extract_imports(self, code: str) -> Set[str]:
        """Extract all import statements from Python code.
        
        Args:
            code: Python source code as string
            
        Returns:
            Set of imported module names (top-level only)
        """
        imports = set()
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning(f"Failed to parse Python code: {e}")
            return imports
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Handle: import foo, import foo.bar
                for alias in node.names:
                    # Get top-level module name (e.g., 'foo' from 'foo.bar.baz')
                    module_name = alias.name.split('.')[0]
                    imports.add(module_name)
                    
            elif isinstance(node, ast.ImportFrom):
                # Handle: from foo import bar, from foo.bar import baz
                if node.module:
                    # Get top-level module name
                    module_name = node.module.split('.')[0]
                    imports.add(module_name)
        
        logger.debug(f"Extracted imports: {imports}")
        return imports
    
    def get_pip_packages(self, imports: Set[str]) -> List[str]:
        """Convert import names to pip package names.
        
        Args:
            imports: Set of imported module names
            
        Returns:
            List of pip package names (excluding standard library)
        """
        packages = []
        
        for module in sorted(imports):
            # Skip standard library modules
            if module in self.stdlib_modules:
                logger.debug(f"Skipping standard library module: {module}")
                continue
            
            # Map import name to package name if different
            package_name = self.IMPORT_TO_PACKAGE.get(module, module)
            
            if package_name not in packages:
                packages.append(package_name)
                logger.debug(f"Mapped {module} -> {package_name}")
        
        return packages
    
    def generate_install_commands(self, packages: List[str]) -> List[str]:
        """Generate pip install commands for packages.
        
        Args:
            packages: List of pip package names
            
        Returns:
            List of pip install command strings
        """
        if not packages:
            return []
        
        # Generate a single pip install command for all packages
        # This is more efficient than multiple RUN commands in Dockerfile
        packages_str = ' '.join(packages)
        command = f"RUN pip install --no-cache-dir {packages_str}"
        
        logger.info(f"Generated install command for {len(packages)} packages")
        return [command]
    
    def analyze_script(self, code: str) -> Dict[str, any]:
        """Analyze a Python script and return dependency information.
        
        Args:
            code: Python source code as string
            
        Returns:
            Dict with keys:
                - 'imports': Set of all imports
                - 'packages': List of pip packages needed
                - 'commands': List of pip install commands for Dockerfile
        """
        imports = self.extract_imports(code)
        packages = self.get_pip_packages(imports)
        commands = self.generate_install_commands(packages)
        
        result = {
            'imports': imports,
            'packages': packages,
            'commands': commands
        }
        
        logger.info(f"Analysis complete: {len(imports)} imports, {len(packages)} packages")
        return result


def analyze_verification_script(script_code: str) -> List[str]:
    """Convenience function to analyze a verification script.
    
    Args:
        script_code: Python verification script code
        
    Returns:
        List of pip install commands to add to Dockerfile
    """
    analyzer = DependencyAnalyzer()
    result = analyzer.analyze_script(script_code)
    return result['commands']
