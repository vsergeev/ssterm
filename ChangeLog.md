* Release 3.0.0 - 10/02/2016
    * Add compatibility for both Python 2 and 3.
    * Add setuptools Python packaging.

* Release 2.0 - 09/16/2014
    * Refactor codebase.
    * Add support for hexadecimal input mode.
    * Add support for piped standard input.
    * Fix handling of removed serial port.
    * Simplify CLI options with output mode and input mode options.
    * Add unit tests for input and output processors.
    * Relicense under MIT license.

* Release 1.7 - 12/16/2013
    * Add support for higher baudrates.
    * Add support for arbitrary baudrates via BOTHER.
    * Clean up codebase some more.

* Release 1.6 - 02/11/2013
    * Switched to gnu_getopt to allow command-line options after serial port device argument.
    * Refactored codebase.

* Release 1.5 - 04/04/2012
    * Fixed escape character bug. Switched escape character from Ctrl-[ to the more unique Ctrl-], which does not serve as the escape code for many other special keys and cause ssterm to quit on them like Ctrl-[ did. Thanks to zzazang for discovering this bug.
    * Modified formatting of split hexadecimal/ASCII representation mode to conform to "hexdump -C" canonical split output.

* Release 1.4 - 03/28/2012
    * Added support for split hexadecimal/ASCII representation mode.
    * Added controlling terminal reset on program quit.
    * Fixed non-blocking read bug.

* Release 1.3 - 03/19/2012
    * Added support for color coding characters / bytes.
    * Rewrote ssterm in Python 2 for ease of future extensibility and maintenance.
    * Upgraded license from GPLv2 to GPLv3.

* Release 1.2 - 02/04/2011
    * Added mutexes for safer handling of shared variables across threads.

* Release 1.1 - 11/22/2009
    * CRITICAL FIX: Serial port was not being opened in non-blocking mode, preventing ssterm from working in some situations. This has been fixed.

* Release 1.0 - 10/26/2009
    * Initial release.
