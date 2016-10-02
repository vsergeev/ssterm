try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='ssterm',
    version='3.0.0',
    description='A simple console-based serial port terminal',
    author='vsergeev',
    author_email='v@sergeev.io',
    url='https://github.com/vsergeev/ssterm',
    py_modules=['ssterm'],
    entry_points={
        'console_scripts': [
            'ssterm=ssterm:main',
        ],
    },
    long_description=
    "ssterm is a simple console-based serial port terminal featuring painless serial port configuration, no dependencies outside of a standard Python 2 or 3 installation, and a variety of useful formatting options:\n"
    "\n"
    "- output modes\n"
    "\n"
    "  - raw\n"
    "  - hexadecimal\n"
    "  - hexadecimal/ASCII split\n"
    "\n"
    "- input modes\n"
    "\n"
    "  - raw\n"
    "  - hexadecimal\n"
    "\n"
    "- transmit newline remapping (e.g. system newline -> CRLF)\n"
    "- receive newline remapping (e.g. CRLF -> system newline)\n"
    "- character color coding\n"
    "- local character echo\n",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Terminals :: Serial",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    license='MIT',
    keywords='serial port uart terminal',
)
