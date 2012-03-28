#!/usr/bin/python2

# ssterm - simple serial-port terminal
# Version 1.4 - March 2012
# Written by Vanya A. Sergeev - <vsergeev@gmail.com>
#
# Copyright (C) 2007-2012 Vanya A. Sergeev
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
import getopt
import select
import re
import string

# Default TTY and Formatting Options
TTY_Options = {'baudrate': 9600, 'databits': 8, 'stopbits': 1, 'parity': "none", 'flowcontrol': "none"}
Format_Options = {'splitmode': False, 'splitfullmode': False, 'hexmode': False, 'txnl': "raw", 'rxnl': "raw", 'hexnl': False, 'echo': False}
Color_Chars = {}
Console_Newline = os.linesep

# Number of columns in hex mode
Hexmode_Columns = 16

# ssterm Quit Escape Character, Ctrl-[ = 0x1B
Quit_Escape_Character = 0x1B

# Default color codes: Black/Red, Black/Green, Black/Yellow, White/Blue,
#  White/Magenta, Black/Cyan, Black/White
Color_Codes = ["\x1b[1;30;41m", "\x1b[1;30;42m", "\x1b[1;30;43m", "\x1b[1;37;44m", "\x1b[1;37;45m", "\x1b[1;30;46m", "\x1b[1;30;47m"]
Color_Code_Reset = "\x1b[0m"

# Valid newline substitution types
Valid_RX_Newline_Type = ["raw", "cr", "lf", "crlf", "crorlf"]
Valid_TX_Newline_Type = ["raw", "none", "cr", "lf", "crlf"]

# Read buffer size
READ_BUFF_SIZE = 4096

###########################################################################
### TTY Helper Functions
###########################################################################

def serial_open(devpath):
	# Open the tty device
	try:
		tty_fd = os.open(devpath, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK);
	except OSError, err:
		sys.stderr.write("Error: opening serial port: %s\n" % str(err))
		return -1

	# Get the current tty options
	# Format: [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
	try:
		tty_attr = termios.tcgetattr(tty_fd)
	except termios.TermiosError, err:
		sys.stderr.write("Error: getting serial port options: %s\n" % str(err))
		return -1

	# Look up the termios baudrate and set it in the attributes structure
	termios_baudrates = {50: termios.B50, 75: termios.B75, 110: termios.B110, 134: termios.B134, 150: termios.B150, 200: termios.B200, 300: termios.B300, 600: termios.B600, 1200: termios.B1200, 1800: termios.B1800, 2400: termios.B2400, 4800: termios.B4800, 9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400, 57600: termios.B57600, 115200: termios.B115200, 230400: termios.B230400}
	if (not TTY_Options['baudrate'] in termios_baudrates):
		sys.stderr.write("Error: Invalid tty baudrate!\n")
		return -1
	tty_attr[4] = termios_baudrates[TTY_Options['baudrate']]
	tty_attr[5] = termios_baudrates[TTY_Options['baudrate']]

	# Reset attributes structure cflag -- tty_attribute[cflag]
	tty_attr[2] = 0

	# Look up and set the appropriate cflag bits in termios_options for a
	# given option, print error message and return -1 for an invalid option
	def termios_cflag_map_and_set(termios_options, option, errmsg):
		if (not option in termios_options):
			sys.stderr.write(errmsg)
			return -1
		tty_attr[2] |= termios_options[option]
		return 0

	# Look up the termios data bits and set it in the attributes structure
	termios_databits = {5: termios.CS5, 6: termios.CS6, 7: termios.CS7, 8: termios.CS8}
	if (termios_cflag_map_and_set(termios_databits, TTY_Options['databits'], "Error: Invalid tty databits!\n") < 0):
		return -1

	# Look up the termios parity and set it in the attributes structure
	termios_parity = {"none": 0, "even": termios.PARENB, "odd": termios.PARENB | termios.PARODD}
	if (termios_cflag_map_and_set(termios_parity, TTY_Options['parity'], "Error: Invalid tty parity!\n") < 0):
		return -1

	# Look up the termios stop bits and set it in the attributes structure
	termios_stopbits = {1: 0, 2: termios.CSTOPB}
	if (termios_cflag_map_and_set(termios_stopbits, TTY_Options['stopbits'], "Error: Invalid tty stop bits!\n") < 0):
		return -1

	# Look up the termios flow control and set it in the attributes structure
	termios_flowcontrol = {"none": 0, "rtscts": termios.CRTSCTS, "xonxoff": 0}
	if (termios_cflag_map_and_set(termios_flowcontrol, TTY_Options['flowcontrol'], "Error: Invalid tty flow control!\n") < 0):
		return -1

	# Enable the receiver
	tty_attr[2] |= (termios.CREAD | termios.CLOCAL);

	# Turn off signals generated for special characters, turn off canonical
	# mode so we can have raw input -- tty_attr[lflag]
	tty_attr[3] = 0

	# Turn off POSIX defined output processing and character mapping/delays
	# so we can have raw output -- tty_attr[oflag]
	tty_attr[1] = 0

	# Ignore break characters -- tty_attr[iflag]
	tty_attr[0] = termios.IGNBRK
	# Enable parity checking if we are using parity -- tty_attr[iflag]
	if (TTY_Options['parity'] != "none"):
		tty_attr[0] |= (termios.INPCK | termios.ISTRIP)
	# Enable XON/XOFF if we are using software flow control
	if (TTY_Options['flowcontrol'] == "xonxoff"):
		tty_attr[0] |= (termios.IXON | termios.IXOFF | termios.IXANY)

	# Set the new tty attributes
	try:
		termios.tcsetattr(tty_fd, termios.TCSANOW, tty_attr)
	except termios.TermiosError, err:
		sys.stderr.write("Error: setting serial port options: %s\n" % str(err))
		return -1

	# Return the tty_fd
	return tty_fd

def serial_close(fd):
	try:
		os.close(fd)
		return 0
	except:
		return -1

def fd_read(fd, n):
	try:
		return (0, os.read(fd, n))
	except OSError, err:
		# Check if non-blocking read returned 0
		if (err.errno == 11): return (0, None)
		else: return (-1, str(err))

def fd_write(fd, data):
	try:
		return (os.write(fd, data), None)
	except OSError, err:
		return (-1, str(err))

###########################################################################
### Read/Write Loop
###########################################################################

# Global variables for console read/write loop
serial_fd = None
stdin_fd = None
txnl_sub = None
rxnl_match = None
stdout_nl_match_save = ''
stdout_cursor_x = 0
stdout_split_bytes = []

def console_init():
	global stdin_fd, txnl_sub, rxnl_match

	stdin_fd = sys.stdin.fileno()

	# Get the current stdin tty options
	# Format: [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
	try:
		stdin_attr = termios.tcgetattr(stdin_fd)
	except termios.TermiosError, err:
		sys.stderr.write("Error: getting stdin tty options: %s\n" % str(err))
		return -1

	# Disable canonical input, so we can send characters without a
	# line feed, and disable echo -- stdin_attr[cflag]
	stdin_attr[3] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
	# Turn off XON/XOFF interpretation so they pass through to the serial
	# port -- stdin_attr[iflag]
	stdin_attr[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)
	# Enable echo if needed
	if (Format_Options['echo']): stdin_attr[3] |= termios.ECHO

	# Set the new stdin tty attributes
	try:
		termios.tcsetattr(stdin_fd, termios.TCSANOW, stdin_attr)
	except termios.TermiosError, err:
		sys.stderr.write("Error: setting stdin tty options: %s\n" % str(err))
		return -1

	# Re-open stdout in unbuffered mode
	sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

	# Look up the appropriate substitution for our transmit newline option
	if Format_Options['txnl'] == "none": txnl_sub = ""
	elif Format_Options['txnl'] == "cr": txnl_sub = "\r"
	elif Format_Options['txnl'] == "crlf": txnl_sub = "\r\n"
	elif Format_Options['txnl'] == "lf": txnl_sub = "\n"
	# "raw" requires no substitution
	else: txnl_sub = None

	# Look up the appropriate matches for our receive newline option
	if Format_Options['rxnl'] == "cr": rxnl_match = "\r"
	elif Format_Options['rxnl'] == "lf": rxnl_match = "\n"
	elif Format_Options['rxnl'] == "crlf": rxnl_match = "\r\n"
	elif Format_Options['rxnl'] == "crorlf": rxnl_match = "\r|\n"
	# "raw" requires no match
	else: rxnl_match = None

def console_reset():
	# Reset stdin terminal for canonical input, echo, and signals

	# Get the current stdin tty options
	# Format: [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
	try:
		stdin_attr = termios.tcgetattr(stdin_fd)
	except termios.TermiosError, err:
		sys.stderr.write("Error: getting stdin tty options: %s\n" % str(err))
		return -1

	# Enable canonical input, echo, signals -- stdin_attr[cflag]
	stdin_attr[3] |= (termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)

	# Set the new stdin tty attributes
	try:
		termios.tcsetattr(stdin_fd, termios.TCSANOW, stdin_attr)
	except termios.TermiosError, err:
		sys.stderr.write("Error: setting stdin tty options: %s\n" % str(err))
		return -1

def console_formatted_print(data):
	global stdout_nl_match_save, stdout_cursor_x, stdout_split_bytes

	if len(data) == 0:
		return

	# Perform receive newline substitutions if necessary
	if rxnl_match != None:
		# If we had a left-over newline character match from before
		if stdout_nl_match_save != '':
			data = stdout_nl_match_save + data
			stdout_nl_match_save = ''

		# Substitute newline matches with console line separator
		data = re.sub(rxnl_match, Console_Newline, data)

		# If the last character is a part of a match, save it for later
		if data[-1] == rxnl_match[0][0]:
			stdout_nl_match_save = data[-1]
			data = data[0:-1]

	# Convert to hex if we're in hex mode
	if Format_Options['hexmode']:
		for x in list(data):
			# Color code this character if it's in our color chars dictionary
			if len(Color_Chars) > 0 and ord(x) in Color_Chars:
				sys.stdout.write(Color_Codes[Color_Chars[ord(x)]] + ("%02X" % ord(x)) + Color_Code_Reset)
			else:
				sys.stdout.write("%02X" % ord(x))
			stdout_cursor_x += 1
			# Pretty print into two columns
			if stdout_cursor_x == Hexmode_Columns/2:
				sys.stdout.write("  ")
			elif stdout_cursor_x == Hexmode_Columns:
				sys.stdout.write("\n")
				stdout_cursor_x = 0
			else:
				sys.stdout.write(" ")
			# Insert a newline if we encounter one and we're
			# interpreting them in hex mode
			# FIXME: This assumes a single character platform newline.
			if x == Console_Newline and Format_Options['hexnl']:
				sys.stdout.write(Console_Newline)
				stdout_cursor_x = 0

	# Convert to split hex-ASCII if we're in split mode
	elif Format_Options['splitmode'] or Format_Options['splitfullmode']:
		# Only print partial strings if we're not in split full mode
		if not Format_Options['splitfullmode']:
			# Delete the current window if we had printed an incomplete one
			if len(stdout_split_bytes) > 0:
				sys.stdout.write("\r")

		def split_print(byte_list):
			# split_print() expects:
			# 1 <= len(byte_list) <= Hexmode_Columns

			# Print the hexadecimal representation
			for i in range(len(byte_list)):
				# Color code this character if it's in our color chars dictionary
				if len(Color_Chars) > 0 and ord(byte_list[i]) in Color_Chars:
					sys.stdout.write(Color_Codes[Color_Chars[ord(byte_list[i])]] + ("%02X" % ord(byte_list[i])) + Color_Code_Reset)
				else:
					sys.stdout.write("%02X" % ord(byte_list[i]))

				# Pretty print into two columns
				if (i+1) == Hexmode_Columns/2:
					sys.stdout.write("  ")
				else:
					sys.stdout.write(" ")

			# Fill up the rest of the hexadecimal representation
			# with blank space
			if len(byte_list) < Hexmode_Columns/2:
				# Account for the pretty print column separator
				sys.stdout.write(" " + " "*(3*(Hexmode_Columns-len(byte_list))))
			elif len(byte_list) < Hexmode_Columns:
				sys.stdout.write(" "*(3*(Hexmode_Columns-len(byte_list))))

			# Print the ASCII representation
			sys.stdout.write("  |")
			for i in range(len(byte_list)):
				# Use the character if it's an ASCII printable
				# character, otherwise use a dot
				if (byte_list[i] in string.letters+string.digits+string.punctuation+' '):
					c = byte_list[i]
				else:
					c = "."
				# Color code this character if it's in our
				# color chars dictionary
				if len(Color_Chars) > 0 and ord(byte_list[i]) in Color_Chars:
					sys.stdout.write(Color_Codes[Color_Chars[ord(byte_list[i])]] + c + Color_Code_Reset)
				else:
					sys.stdout.write(c)
			sys.stdout.write("|")

		for x in list(data):
			# Add to our split byte window
			stdout_split_bytes.append(x)
			# If we get a full column window, print it out with a
			# newline
			if (len(stdout_split_bytes) == Hexmode_Columns):
				split_print(stdout_split_bytes)
				sys.stdout.write(Console_Newline)
				stdout_split_bytes = []

		# Only print partial strings if we're not in split full mode
		if not Format_Options['splitfullmode']:
			# Print out any bytes left in our window
			if len(stdout_split_bytes) > 0:
				split_print(stdout_split_bytes)


	# Normal print
	else:
		# Apply Color coding if necessary
		if len(Color_Chars) > 0:
			# Unfortunately, for generality, we can't do a global
			# regex substitution on data with the color-coded
			# version, since we could have potentially selected
			# color code characters that are present in the ANSI
			# color escape sequences. So we operate on the data
			# a char at time here.
			for x in list(data):
				# Color code this character if it's in our color chars dictionary
				if ord(x) in Color_Chars:
					sys.stdout.write(Color_Codes[Color_Chars[ord(x)]] + x + Color_Code_Reset)
				else:
					sys.stdout.write(x)
		else:
			sys.stdout.write(data)


def console_read_write_loop():
	# Select between serial port and stdin file descriptors
	read_fds = [serial_fd, stdin_fd]
	while True:
		ready_read_fds, ready_write_fds, ready_excep_fds = select.select(read_fds, [], [])

		if stdin_fd in ready_read_fds:
			# Read a buffer from stdin
			retval, buff = fd_read(stdin_fd, READ_BUFF_SIZE)
			if retval < 0:
				sys.stderr.write("Error: reading stdin: %s\n" % buff)
				break
			if buff and len(buff) > 0:
				# Perform transmit newline subsitutions if
				# necessary FIXME: This assumes a single
				# character platform newline.
				if txnl_sub != None:
					buff = map(lambda x: txnl_sub if x == Console_Newline else x, list(buff))
					buff = ''.join(buff)

				# If we detect the escape character, then quit
				if chr(Quit_Escape_Character) in buff:
					break

				# Write the buffer to the serial port
				retval, err = fd_write(serial_fd, buff)
				if retval < 0:
					sys.stderr.write("Error: writing to serial port: %s\n" % err)

		if serial_fd in ready_read_fds:
			# Read a buffer from the serial port
			retval, buff = fd_read(serial_fd, READ_BUFF_SIZE)
			if retval < 0:
				sys.stderr.write("Error: reading serial port: %s\n" % buff)
				break
			if buff and len(buff) > 0:
				console_formatted_print(buff)


###########################################################################
### Command-Line Options Parsing
###########################################################################

def print_usage():
	print "Usage: %s [options] <serial port>\n" % sys.argv[0]
	print "\
ssterm - simple serial-port terminal\n\
Written by Vanya A. Sergeev - <vsergeev@gmail.com>.\n\
\n\
 Serial Port Options:\n\
  -b, --baudrate <rate>         Specify the baudrate\n\
  -d, --databits <number>       Specify the number of data bits [5,6,7,8]\n\
  -p, --parity <type>           Specify the parity [none, odd, even]\n\
  -t, --stopbits <number>       Specify number of stop bits [1,2]\n\
  -f, --flow-control <type>     Specify the flow-control [none, rtscts, xonxoff]\n\
\n\
 Formatting Options:\n\
  -s, --split                   Split hexadecimal/ASCII mode\n\
\n\
  --split-full			Split hexadecimal/ASCII mode with full lines\n\
                                 (good for piping)\n\
\n\
  -x, --hex                     Pure hexadecimal mode\n\
  --hex-nl                      Print newlines in pure hexadecimal mode\n\
\n\
  -c, --color <list>            Specify comma-delimited list of characters in\n\
                                 ASCII or hex to color code: A,$,_,0x0d,0x0a ...\n\
\n\
  --tx-nl <substitution>        Specify the transmit newline substitution\n\
                                 [raw, none, cr, lf, crlf]\n\
  --rx-nl <match>               Specify the receive newline match\n\
                                 [raw, cr, lf, crlf, crorlf]\n\
\n\
  -e, --echo                    Turn on local character echo\n\
\n\
  -h, --help                    Display this usage/help\n\
  -v, --version                 Display the program's version\n\n"
	print "\
Quit Escape Character:          Ctrl-[\n\
\n\
Color Code Sequence (fg/bg):\n\
 Black/Red, Black/Green, Black/Yellow, White/Blue, White/Magenta,\n\
 Black/Cyan, Black/White\n\
\n\
Default Options:\n\
 baudrate: 9600 | databits: 8 | parity: none | stopbits: 1 | flow control: none\n\
 tx newline: raw | rx newline: raw | local echo: off\n\
 split mode: off | hex mode: off   | color code: off\n"

def print_version():
	print "ssterm version 1.4 - 03/28/2012"

def int_handled(x, base=10):
	try:
		return int(x, base)
	except:
		return None

# Parse options
try:
	options, args = getopt.getopt(sys.argv[1:], "b:d:p:t:f:esxhvc:", ["baudrate=", "databits=", "parity=", "stopbits=", "flowcontrol=", "tx-nl=", "rx-nl=", "echo", "split", "split-full", "hex", "hex-nl", "color-nl", "help", "version", "color="])
except getopt.GetoptError, err:
	print str(err), "\n"
	print_usage()
	sys.exit(-1)


# Update options containers
for opt_c, opt_arg in options:
	if opt_c in ("-b", "--baudrate"):
		TTY_Options['baudrate'] = int_handled(opt_arg)
		if TTY_Options['baudrate'] == None:
			sys.stderr.write("Error: Invalid tty baudrate!\n")
			sys.exit(-1)

	elif opt_c in ("-d", "--databits"):
		TTY_Options['databits'] = int_handled(opt_arg)
		if TTY_Options['databits'] == None:
			sys.stderr.write("Error: Invalid tty data bits!\n")
			sys.exit(-1)

	elif opt_c in ("-p", "--parity"):
		TTY_Options['parity'] = opt_arg

	elif opt_c in ("-t", "--stopbits"):
		TTY_Options['stopbits'] = int_handled(opt_arg)
		if TTY_Options['stopbits'] == None:
			sys.stderr.write("Error: Invalid tty stop bits!\n")
			sys.exit(-1)

	elif opt_c in ("-f", "--flowcontrol"):
		TTY_Options['flowcontrol'] = opt_arg

	elif opt_c in ("-e", "--echo"):
		Format_Options['echo'] = True

	elif opt_c in ("-s", "--split"):
		Format_Options['splitmode'] = True

	elif opt_c in ("--split-full"):
		Format_Options['splitfullmode'] = True

	elif opt_c in ("-x", "--hex"):
		Format_Options['hexmode'] = True

	elif opt_c in ("-c", "--color"):
		opt_arg = filter(lambda x: len(x) >= 1, opt_arg.split(","))
		if len(opt_arg) > len(Color_Codes):
			sys.stderr.write("Error: Maximum color code characters (%d) exceeded!\n" % len(Color_Codes))
			sys.exit(-1)
		# Parse ASCII and hex encoded characters into our Color_Chars dictionary
		for c in opt_arg:
			if len(c) == 1:
				Color_Chars[ord(c)] = len(Color_Chars)
			elif len(c) > 2 and c[0:2] == "0x":
				c_int = int_handled(c, 16)
				if c_int == None:
					sys.stderr.write("Error: Unknown color code character: %s\n" % c)
					sys.exit(-1)
				Color_Chars[c_int] = len(Color_Chars)
			else:
				sys.stderr.write("Error: Unknown color code character: %s\n" % c)
				sys.exit(-1)

	elif opt_c == "--tx-nl":
		Format_Options['txnl'] = opt_arg
		if (not Format_Options['txnl'] in Valid_TX_Newline_Type):
			sys.stderr.write("Error: Invalid tx newline type!\n")
			print_usage()
			sys.exit(-1)

	elif opt_c == "--rx-nl":
		Format_Options['rxnl'] = opt_arg
		if (not Format_Options['rxnl'] in Valid_RX_Newline_Type):
			sys.stderr.write("Error: Invalid rx newline type!\n")
			print_usage()
			sys.exit(-1)

	elif opt_c == "--hex-nl":
		Format_Options['hexnl'] = True

	elif opt_c in ("-h", "--help"):
		print_usage()
		sys.exit(0)

	elif opt_c in ("-v", "--version"):
		print_version()
		sys.exit(0)


# Make sure the serial port device is specified
if len(args) < 1:
	print_usage()
	sys.exit(-1)

# Open the serial port with our options
serial_fd = serial_open(args[0])
if (serial_fd < 0):
	sys.exit(-1)

console_init()
console_read_write_loop()
sys.stdout.write("\n")
console_reset()

# Close the serial port
serial_close(serial_fd)

