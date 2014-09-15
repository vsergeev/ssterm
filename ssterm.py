#!/usr/bin/env python2

# ssterm - simple serial-port terminal
# Version 1.8 - September 2014
# Vanya A. Sergeev - <vsergeev@gmail.com>
# https://github.com/vsergeev/ssterm
#
# Copyright (C) 2007-2014 Vanya A. Sergeev
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import sys
import os
import termios
import select
import errno
import getopt
import re
import string

###############################################################################
### Default Options
###############################################################################

# Default TTY Options
TTY_Options = {
                'baudrate': 115200,
                'databits': 8,
                'stopbits': 1,
                'parity': "none",
                'flow_control': "none"
            }

# Default Formatting Options
Format_Options = {
                'output_mode': 'raw',       # 'split', 'splitfull', 'hex', 'hexnl'
                'input_mode': 'raw',        # 'hex'
                'transmit_newline': "raw",  # 'cr', 'crlf', 'lf', 'none'
                'receive_newline': "raw",   # 'cr', 'crlf', 'lf', 'crorlf'
                'echo': False,
                'color_chars': {},          # { ord('\n'), ord('A') }
            }

###############################################################################
### Program Constants
###############################################################################

# Quit Escape Character: Ctrl-] = 0x1D
Quit_Escape_Character = 0x1D

# Number of columns in hexadecimal print mode
Hexadecimal_Columns = 16

# Default color codes:
#   Black/Red, Black/Green, Black/Yellow,
#   White/Blue, White/Magenta, Black/Cyan,
#   Black/White
Color_Codes = [ "\x1b[1;30;41m", "\x1b[1;30;42m", "\x1b[1;30;43m",
                "\x1b[1;37;44m", "\x1b[1;37;45m", "\x1b[1;30;46m",
                "\x1b[1;30;47m"]
Color_Code_Reset = "\x1b[0m"

# Read buffer size
READ_BUF_SIZE = 4096

# Newline Substitution tables
RX_Newline_Sub = {'raw': None, 'cr': "\r", 'crlf': "\r\n", 'lf': "\n", 'crorlf': "\r|\n"}
TX_Newline_Sub = {'raw': None, 'cr': "\r", 'crlf': "\r\n", 'lf': "\n", 'none': ""}

###############################################################################
### Serial Helper Functions
###############################################################################

def serial_open(device_path, baudrate, databits, stopbits, parity, flow_control):
    # Open the tty device
    try:
        fd = os.open(device_path, os.O_RDWR | os.O_NOCTTY)
    except OSError as err:
        raise Exception("%s" % str(err))

    # Get current termios attributes
    #   [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
    try:
        tty_attr = termios.tcgetattr(fd)
    except termios.error as err:
        raise Exception("Getting serial port options: %s" % str(err))

    ######################################################################
    ### cflag, ispeed, ospeed
    ######################################################################

    # Reset cflag: Enable receiver, ignore modem control lines
    tty_attr[2] = (termios.CREAD | termios.CLOCAL)

    # Look up the termios baudrate and set it in the attributes structure
    #   tty_attr[cflag], tty_attr[ispeed], tty_attr[ospeed]
    termios_baudrates = {
        50: termios.B50, 75: termios.B75, 110: termios.B110, 134: termios.B134,
        150: termios.B150, 200: termios.B200, 300: termios.B300,
        600: termios.B600, 1200: termios.B1200, 1800: termios.B1800,
        2400: termios.B2400, 4800: termios.B4800, 9600: termios.B9600,
        19200: termios.B19200, 38400: termios.B38400, 57600: termios.B57600,
        115200: termios.B115200, 230400: termios.B230400,
        # Linux baudrates bits missing in termios module included below
        460800: 0x1004, 500000: 0x1005, 576000: 0x1006,
        921600: 0x1007, 1000000: 0x1008, 1152000: 0x1009,
        1500000: 0x100A, 2000000: 0x100B, 2500000: 0x100C,
        3000000: 0x100D, 3500000: 0x100E, 4000000: 0x100F,
    }

    if baudrate in termios_baudrates:
        tty_attr[2] |= termios_baudrates[baudrate]
        tty_attr[4] = termios_baudrates[baudrate]
        tty_attr[5] = termios_baudrates[baudrate]
    else:
        # Set alternate speed via BOTHER (=0x1000) cflag,
        # Pass baudrate directly in ispeed, ospeed
        tty_attr[2] |= 0x1000
        tty_attr[4] = baudrate
        tty_attr[5] = baudrate

    # Look up and set the appropriate cflag bits in termios_options for a given
    # option
    def termios_cflag_map_and_set(termios_options, option, errmsg):
        if not option in termios_options:
            raise ValueError(errmsg)
        tty_attr[2] |= termios_options[option]

    # Look up the termios data bits and set it in the attributes structure
    termios_databits = {5: termios.CS5, 6: termios.CS6, 7: termios.CS7, 8: termios.CS8}
    termios_cflag_map_and_set(termios_databits, databits, "Invalid tty databits!")
    # Look up the termios parity and set it in the attributes structure
    termios_parity = {"none": 0, "even": termios.PARENB, "odd": termios.PARENB | termios.PARODD}
    termios_cflag_map_and_set(termios_parity, parity, "Invalid tty parity!")
    # Look up the termios stop bits and set it in the attributes structure
    termios_stopbits = {1: 0, 2: termios.CSTOPB}
    termios_cflag_map_and_set(termios_stopbits, stopbits, "Invalid tty stop bits!")
    # Look up the termios flow control and set it in the attributes structure
    termios_flowcontrol = {"none": 0, "rtscts": termios.CRTSCTS, "xonxoff": 0}
    termios_cflag_map_and_set(termios_flowcontrol, flow_control, "Invalid tty flow control!")

    ######################################################################
    ### lflag
    ######################################################################

    # Turn off signals generated for special characters, turn off canonical
    # mode so we can have raw input -- tty_attr[lflag]
    tty_attr[3] = 0

    ######################################################################
    ### oflag
    ######################################################################

    # Turn off POSIX defined output processing and character mapping/delays
    # so we can have raw output -- tty_attr[oflag]
    tty_attr[1] = 0

    ######################################################################
    ### iflag
    ######################################################################

    # Ignore break characters -- tty_attr[iflag]
    tty_attr[0] = termios.IGNBRK
    # Enable parity checking if we are using parity -- tty_attr[iflag]
    if parity != "none":
        tty_attr[0] |= (termios.INPCK | termios.ISTRIP)
    # Enable XON/XOFF if we are using software flow control
    if flow_control == "xonxoff":
        tty_attr[0] |= (termios.IXON | termios.IXOFF | termios.IXANY)

    # Set new termios attributes
    try:
        termios.tcsetattr(fd, termios.TCSANOW, tty_attr)
    except termios.error as err:
        raise Exception("Setting serial port options: %s" % str(err))

    # Return the fd
    return fd

def serial_close(fd):
    os.close(fd)

###############################################################################
### TTY Helper Functions
###############################################################################

def stdin_raw_open(echo):
    fd = sys.stdin.fileno()

    # Get the current stdin tty options
    #   [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
    try:
        stdin_attr = termios.tcgetattr(fd)
    except termios.error as err:
        raise Exception("Getting stdin tty options: %s" % str(err))

    # Disable canonical input, so we can send characters without a line
    # feed, disable signal interpretation, and disable echo
    # -- stdin_attr[cflag]
    stdin_attr[3] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)

    # Enable echo if needed
    if echo:
        stdin_attr[3] |= termios.ECHO

    # Turn off XON/XOFF interpretation so they pass through to the serial
    # port -- stdin_attr[iflag]
    stdin_attr[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)

    # Set the new stdin tty attributes
    try:
        termios.tcsetattr(fd, termios.TCSANOW, stdin_attr)
    except termios.error as err:
        raise Exception("Setting stdin tty options: %s" % str(err))

    return fd

def stdout_raw_open():
    # Re-open stdout in unbuffered mode
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    return sys.stdout.fileno()

def stdin_reset():
    fd = sys.stdin.fileno()

    # Reset stdin terminal for canonical input, echo, and signals

    # Get the current stdin tty options
    #   [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
    try:
        stdin_attr = termios.tcgetattr(fd)
    except termios.error as err:
        raise Exception("Getting stdin tty options: %s" % str(err))

    # Enable canonical input, echo, signals -- stdin_attr[cflag]
    stdin_attr[3] |= (termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)

    # Re-enable XON/XOFF interpretation -- stdin_attr[iflag]
    stdin_attr[0] |= (termios.IXON | termios.IXOFF | termios.IXANY)

    # Set the new stdin tty attributes
    try:
        termios.tcsetattr(fd, termios.TCSANOW, stdin_attr)
    except termios.error as err:
        raise Exception("Setting stdin tty options: %s" % str(err))

###############################################################################
### Input Processors
###############################################################################

def input_processor_newline(sub):
    # Substitute console newline in buf with sub
    def f(buf):
        # FIXME: This assumes a single character platform newline.
        return buf.replace(os.linesep, sub)
    return f

def input_processor_hexadecimal():
    # State to keep track of consecutive hex characters
    state = [""]
    # Interpret hexadecimal characters in buf
    def f(buf):
        nbuf = ""
        for c in buf:
            if c in string.hexdigits:
                state[0] += c
            # Reset our state if we encounter a none hex character
            else:
                state[0] = ""

            # Convert 2 consecutive hex characters
            if len(state[0]) == 2:
                nbuf += chr(int(state[0], 16))
                state[0] = ""
        return nbuf
    return f

###############################################################################
### Output Processors
###############################################################################

def output_processor_newline(sub):
    # State to keep track of cut-off newline sequences
    state = [""]
    # Substitute sub in buf with console newline
    def f(buf):
        # Append our left-over newline character match from before
        buf = state[0] + buf
        state[0] = ""

        # Substitute newline matches with console newline
        buf = re.sub(sub, os.linesep, buf)

        # If the last character is a part of a match, chop it off and save it
        # for later
        if len(buf) > 0 and buf[-1] == sub[0]:
            state[0] = buf[-1]
            buf = buf[:-1]

        return buf
    return f

def output_processor_raw(color_chars):
    # If we're not color coding
    if len(color_chars) == 0:
        # Identity function
        def f(buf):
            return buf
        return f

    # Color code characters in buf
    def f(buf):
        # Unfortunately, we can't do a global regex substitution on data with
        # its color-coded version, since we could have potentially selected
        # color code characters that are present in the ANSI color escape
        # sequences in subsequent substitutions. So we operate on the data a
        # character at time here.
        nbuf = ""
        for c in buf:
            if ord(c) in color_chars:
                nbuf += Color_Codes[color_chars[ord(c)]] + c + Color_Code_Reset
            else:
                nbuf += c
        return nbuf
    return f

def output_processor_hexadecimal(color_chars, interpret_newlines=False):
    # State to keep track of our x position
    state = [0]
    # Format buffer into 2-column hexadecimal representation, with optional
    # color coding and newline interpretation.
    def f(buf):
        nbuf = ""
        for c in buf:
            # Color code this character if it's in our color chars dictionary
            if len(color_chars) > 0 and ord(c) in color_chars:
                nbuf += Color_Codes[color_chars[ord(c)]] + ("%02x" % ord(c)) + Color_Code_Reset
            else:
                nbuf += "%02x" % ord(c)

            state[0] += 1

            # Pretty print into two columns
            if state[0] == Hexadecimal_Columns/2:
                nbuf += "  "
            elif state[0] == Hexadecimal_Columns:
                nbuf += os.linesep
                state[0] = 0
            else:
                nbuf += " "

            # Insert a newline if we encounter one and we're interpreting them
            # FIXME: This assumes a single character platform newline.
            if interpret_newlines and c == os.linesep:
                nbuf += os.linesep
                state[0] = 0
        return nbuf
    return f

def output_processor_split(color_chars, partial_lines=True):
    # Helper function to format one line of split hexadecimal/ASCII
    # representation with optional color coding.
    def format_split_line(buf):
        nbuf = ""
        # Format the hexadecimal representation
        for i in range(len(buf)):
            # Color code this character if it's in our color chars
            if len(color_chars) > 0 and ord(buf[i]) in color_chars:
                nbuf += Color_Codes[color_chars[ord(buf[i])]] + ("%02x" % ord(buf[i])) + Color_Code_Reset
            else:
                nbuf += "%02x" % ord(buf[i])

            # Pretty print into two columns
            if (i+1) == Hexadecimal_Columns/2:
                nbuf += "  "
            else:
                nbuf += " "

        # Format hexadecimal column blank spaces
        if len(buf) < Hexadecimal_Columns/2:
            # Account for the pretty print column separator
            nbuf += " " + " "*(3*(Hexadecimal_Columns-len(buf)))
        else:
            nbuf += " "*(3*(Hexadecimal_Columns-len(buf)))

        # Format the ASCII representation
        nbuf += " |"
        for i in range(len(buf)):
            c = "."

            # Use the character if it's an ASCII printable character, otherwise use
            # a dot
            if buf[i] in string.letters+string.digits+string.punctuation+' ':
                c = buf[i]

            # Color code this character if it's in our color chars
            if len(color_chars) > 0 and ord(buf[i]) in color_chars:
                nbuf += Color_Codes[color_chars[ord(buf[i])]] + c + Color_Code_Reset
            else:
                nbuf += c

        # Format ASCII column blank spaces
        if len(buf) < Hexadecimal_Columns:
            nbuf += " "*(Hexadecimal_Columns-len(buf))

        nbuf += "|"

        return nbuf

    # State to keep track of bytes on the current line
    state = [""]
    # Format buf into a split hexadecimal/ASCII representation, with optional
    # color coding.
    def f(buf):
        if len(buf) == 0:
            return ""

        nbuf = ""

        state[0] += buf

        # Erase current partial line with \r
        if partial_lines and len(state[0]) > 0:
            nbuf += "\r"

        # Process each full line at a time
        for i in range(0, len(state[0]), Hexadecimal_Columns):
            line = state[0][i:i+Hexadecimal_Columns]

            if len(line) < Hexadecimal_Columns:
                if partial_lines:
                    nbuf += format_split_line(line)
            else:
                nbuf += format_split_line(line)
                nbuf += os.linesep

        # Remove processed full lines from our state
        state[0] = state[0][len(state[0])-(len(state[0]) % Hexadecimal_Columns):len(state[0])]
        return nbuf
    return f

###############################################################################
### Main Read/Write Loop
###############################################################################

def read_write_loop(serial_fd, stdin_fd, stdout_fd):
    ### Prepare our input pipeline
    input_pipeline = []
    # Hexadecimal interpretation
    if Format_Options['input_mode'] == "hex":
        input_pipeline.append(input_processor_hexadecimal())
    # Transmit newline substitution
    if TX_Newline_Sub[Format_Options['transmit_newline']] is not None:
        input_pipeline.append(input_processor_newline(TX_Newline_Sub[Format_Options['transmit_newline']]))

    ### Prepare our output pipeline
    output_pipeline = []
    # Receive newline substitution
    if RX_Newline_Sub[Format_Options['receive_newline']] is not None:
        output_pipeline.append(output_processor_newline(RX_Newline_Sub[Format_Options['receive_newline']]))
    # Raw mode
    if Format_Options['output_mode'] == 'raw':
        output_pipeline.append(output_processor_raw(Format_Options['color_chars']))
    # Split mode
    elif Format_Options['output_mode'] == 'split':
        output_pipeline.append(output_processor_split(Format_Options['color_chars']))
    # Split full mode
    elif Format_Options['output_mode'] == 'splitfull':
        output_pipeline.append(output_processor_split(Format_Options['color_chars'], partial_lines=False))
    # Hexadecimal mode
    elif Format_Options['output_mode'] == 'hex':
        output_pipeline.append(output_processor_hexadecimal(Format_Options['color_chars']))
    # Hexadecimal with newlines mode
    elif Format_Options['output_mode'] == 'hexnl':
        output_pipeline.append(output_processor_hexadecimal(Format_Options['color_chars'], interpret_newlines=True))

    # Select between serial port and stdin file descriptors
    read_fds = [serial_fd, stdin_fd]

    while True:
        ready_read_fds, _, _ = select.select(read_fds, [], [])

        if stdin_fd in ready_read_fds:
            # Read a buffer from stdin
            try:
                buf = os.read(stdin_fd, READ_BUF_SIZE)
            except Exception as err:
                raise Exception("Error reading stdin: %s\n" % str(err))

            # If we detect the escape character, quit
            if chr(Quit_Escape_Character) in buf:
                break

            # Process the buffer through our input pipeline
            for f in input_pipeline:
                buf = f(buf)

            # Write the buffer to the serial port
            try:
                os.write(serial_fd, buf)
            except Exception as err:
                raise Exception("Error writing to serial port: %s\n" % str(err))

        if serial_fd in ready_read_fds:
            # Read a buffer from the serial port
            try:
                buf = os.read(serial_fd, READ_BUF_SIZE)
            except Exception as err:
                raise Exception("Error reading serial port: %s\n" % str(err))

            # Break if we hit "EOF"
            if len(buf) == 0:
                break

            # Process the buffer through our output pipeline
            for f in output_pipeline:
                buf = f(buf)

            # Write the buffer to stdout
            try:
                os.write(stdout_fd, buf)
            except Exception as err:
                raise Exception("Error writing to stdout: %s\n" % str(err))

###############################################################################
### Command-Line Options Parsing and Help
###############################################################################

def print_usage():
    print "Usage: %s [options] <serial port device>\n" % sys.argv[0]
    print "\
ssterm - simple serial-port terminal v1.8\n\
Vanya A. Sergeev - <vsergeev@gmail.com>\n\
https://github.com/vsergeev/ssterm\n\
\n\
Serial Port Options:\n\
  -b, --baudrate <rate>         Specify baudrate (e.g. 9600, 115200, etc.)\n\
  -d, --databits <number>       Specify number of data bits [5,6,7,8]\n\
  -p, --parity <type>           Specify parity [none, odd, even]\n\
  -t, --stopbits <number>       Specify number of stop bits [1,2]\n\
  -f, --flow-control <type>     Specify flow-control [none, rtscts, xonxoff]\n\
\n\
Output Formatting Options:\n\
  -o, --output <mode>           Specify output mode\n\
                                  raw       raw (default)\n\
                                  split     hex./ASCII split\n\
                                  splitfull hex./ASCII split with full lines\n\
                                  hex       hex.\n\
                                  hexnl     hex. with newlines\n\
\n\
  --rx-nl <substitution>        Enable receive newline substitution\n\
                                  [raw, cr, lf, crlf, crorlf]\n\
\n\
  -c, --color <list>            Specify comma-delimited list of characters in\n\
                                  ASCII or hex. to color code: A,$,0x0d,0x0a,...\n\
\n\
Input Formatting Options:\n\
  -i, --input <mode>            Specify input mode\n\
                                  raw       raw (default)\n\
                                  hex       hex. interpretaion\n\
\n\
  --tx-nl <substitution>        Enable transmit newline substitution\n\
                                  [raw, none, cr, lf, crlf]\n\
\n\
  -e, --echo                    Enable local character echo\n\
\n\
Miscellaneous:\n\
  -h, --help                    Display this usage/help\n\
  -v, --version                 Display the program's version\n\n"
    print "\
Quit Escape Character:          Ctrl-]\n\
\n\
Default Options:\n\
 baudrate: 115200 | databits: 8 | parity: none | stopbits: 1 | flowctrl: none\n\
 output mode: raw | rx newline: raw | color code: off\n\
 input mode: raw  | tx newline: raw | local echo: off\n"

def print_version():
    print "ssterm version 1.8 - 09/13/2014"

if __name__ == '__main__':
    # Parse options
    try:
        options, args = getopt.gnu_getopt(sys.argv[1:], "b:d:p:t:f:o:c:i:ehv", ["baudrate=", "databits=", "parity=", "stopbits=", "flow-control=", "output=", "color=", "rx-nl=", "input=", "tx-nl=", "echo", "help", "version"])
    except getopt.GetoptError, err:
        print str(err), "\n"
        print_usage()
        sys.exit(-1)

    # Update options containers
    for opt_c, opt_arg in options:
        # Serial port options
        if opt_c in ("-b", "--baudrate"):
            try:
                TTY_Options['baudrate'] = int(opt_arg, 10)
            except ValueError:
                sys.stderr.write("Error: Invalid tty baudrate!\n")
                sys.exit(-1)
        elif opt_c in ("-d", "--databits"):
            try:
                TTY_Options['databits'] = int(opt_arg, 10)
            except ValueError:
                sys.stderr.write("Error: Invalid tty data bits!\n")
                sys.exit(-1)
        elif opt_c in ("-p", "--parity"):
            TTY_Options['parity'] = opt_arg
        elif opt_c in ("-t", "--stopbits"):
            try:
                TTY_Options['stopbits'] = int(opt_arg, 10)
            except ValueError:
                sys.stderr.write("Error: Invalid tty stop bits!\n")
                sys.exit(-1)
        elif opt_c in ("-f", "--flow-control"):
            TTY_Options['flow_control'] = opt_arg

        # Output Formatting Options
        elif opt_c in ("-o", "--output"):
            if not opt_arg in ["raw", "split", "splitfull", "hex", "hexnl"]:
                sys.stderr.write("Error: Invalid output mode!\n")
                print_usage()
                sys.exit(-1)
            Format_Options['output_mode'] = opt_arg
        elif opt_c == "--tx-nl":
            if not opt_arg in TX_Newline_Sub:
                sys.stderr.write("Error: Invalid tx newline type!\n")
                print_usage()
                sys.exit(-1)
            Format_Options['transmit_newline'] = opt_arg
        elif opt_c in ("-c", "--color"):
            opt_arg = filter(lambda x: len(x) >= 1, opt_arg.split(","))
            if len(opt_arg) > len(Color_Codes):
                sys.stderr.write("Error: Maximum color code characters (%d) exceeded!\n" % len(Color_Codes))
                sys.exit(-1)
            # Parse ASCII and hex encoded characters into our color_chars dictionary
            for c in opt_arg:
                # ASCII character
                if len(c) == 1:
                    Format_Options['color_chars'][ord(c)] = len(Format_Options['color_chars'])
                # Hexadecimal number
                elif len(c) > 2 and c[0:2] == "0x":
                    try:
                        c_int = int(c, 16)
                    except ValueError:
                        sys.stderr.write("Error: Unknown color code character: %s\n" % c)
                        sys.exit(-1)
                    Format_Options['color_chars'][c_int] = len(Format_Options['color_chars'])
                # Unknown
                else:
                    sys.stderr.write("Error: Unknown color code character: %s\n" % c)
                    sys.exit(-1)

        # Input Formatting Options
        elif opt_c in ("-i", "--input"):
            if not opt_arg in ["raw", "hex"]:
                sys.stderr.write("Error: Invalid input mode!\n")
                print_usage()
                sys.exit(-1)
            Format_Options['input_mode'] = opt_arg
        elif opt_c == "--rx-nl":
            if not opt_arg in RX_Newline_Sub:
                sys.stderr.write("Error: Invalid rx newline type!\n")
                print_usage()
                sys.exit(-1)
            Format_Options['receive_newline'] = opt_arg
        elif opt_c in ("-e", "--echo"):
            Format_Options['echo'] = True

        # Miscellaneous Options
        elif opt_c in ("-h", "--help"):
            print_usage()
            sys.exit(0)
        elif opt_c in ("-v", "--version"):
            print_version()
            sys.exit(0)

    # Make sure a serial port device is specified
    if len(args) < 1:
        print_usage()
        sys.exit(-1)

    # Open the serial port with our options
    try:
        serial_fd = serial_open(args[0], TTY_Options['baudrate'], TTY_Options['databits'], TTY_Options['stopbits'], TTY_Options['parity'], TTY_Options['flow_control'])
    except Exception as err:
        sys.stderr.write("Error opening serial port: %s\n" % str(err))
        sys.exit(-1)

    # Open stdin in raw mode
    try:
        stdin_fd = stdin_raw_open(Format_Options['echo'])
    except Exception as err:
        sys.stderr.write("Error opening stdin in raw mode: %s\n" % str(err))
        sys.exit(-1)

    # Open stdout in raw mode
    try:
        stdout_fd = stdout_raw_open()
    except Exception as err:
        sys.stderr.write("Error opening stdout in raw mode: %s\n" % str(err))
        sys.exit(-1)

    # Enter main read/write loop
    try:
        read_write_loop(serial_fd, stdin_fd, stdout_fd)
    except Exception as err:
        sys.stderr.write("%s\n" % str(err))
        sys.exit(-1)

    print ""

    # Reset stdin to buffered mode
    try:
        stdin_reset()
    except Exception as err:
        sys.stderr.write("Error resetting stdin to buffered mode: %s\n" % str(err))
        sys.exit(-1)

    # Close the serial port
    try:
        serial_close(serial_fd)
    except Exception as err:
        sys.stderr.write("Error closing serial port: %s\n" % str(err))
        sys.exit(-1)

