/* 
 * ssterm - simple serial-port terminal.
 * Version 1.1 - 2009/11
 * Written by Vanya A. Sergeev - <vsergeev@gmail.com>
 *
 * Copyright (C) 2009 Vanya A. Sergeev
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA. 
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <signal.h>
#include <pthread.h>
#include <curses.h>
#include <errno.h>
#include <getopt.h>

/* Much of the dirty work is keeping the circular receive buffer printing 
 * cleanly with the fixed size and non-wrapping curses pad, which displays the
 * actual data. */

/* Todo:
	* write file configuration backend
	* custom color coded characters?

	* lock file support?
	* fixed pad, redraw buffer window each time?
	
	* sending control characters
	* setting control lines
*/

/******************************************************************************
 ******************************************************************************
 ******************************************************************************/

/* Possible error codes for tty configure, read, write functions */
#define	ERROR_ERRNO		-1
#define ERROR_BAUDRATE		-2
#define ERROR_DATABITS		-3
#define ERROR_PARITY		-4
#define ERROR_STOPBITS		-5
#define ERROR_FLOWCONTROL	-6

/* Options for the serial port */
#define PARITY_NONE		0
#define PARITY_ODD		1
#define PARITY_EVEN		2
#define FLOW_CONTROL_NONE	0
#define FLOW_CONTROL_RTSCTS	1
#define FLOW_CONTROL_XONXOFF	2

#define PARITY_NONE_STR			"none"
#define PARITY_ODD_STR			"odd"
#define PARITY_EVEN_STR			"even"
#define FLOW_CONTROL_NONE_STR		"none"
#define FLOW_CONTROL_RTSCTS_STR		"rtscts"
#define FLOW_CONTROL_XONXOFF_STR	"xonxoff"
#define NEWLINE_NONE_STR		"none"
#define NEWLINE_CR_STR			"cr"
#define NEWLINE_LF_STR			"lf"
#define NEWLINE_CRLF_STR		"crlf"
#define NEWLINE_CRORLF_STR		"crorlf"
#define NEWLINE_RAW_STR			"raw"

/* Special curses key definitions */
#define CTRL_C		0x03
#define CTRL_D		0x04
#define CTRL_H		0x08
#define CTRL_L		0x0C
#define CTRL_N		0x0E
#define CTRL_O		0x0F
#define CTRL_R		0x12

/* Signals to the read thread */
#define SIGNAL_RTH_EXIT			(1<<0)
#define SIGNAL_RTH_SCREEN_REFRESH	(1<<1)
#define SIGNAL_RTH_BUFFER_CLEAR		(1<<2)
#define SIGNAL_RTH_BUFFER_DUMP		(1<<3)

/* Screen modes */
#define UI_OPTION_STDIN_STDOUT		(1<<0)
#define UI_OPTION_ECHO			(1<<1)
#define	UI_OPTION_HEX			(1<<2)
#define UI_OPTION_HEX_NEWLINE		(1<<3)
#define UI_OPTION_COLOR_CODED		(1<<4)

/* CR and LF mapping bits */
#define OPTION_NEWLINE_NONE	0
#define	OPTION_NEWLINE_CR	(1<<0)
#define OPTION_NEWLINE_LF	(1<<1)
#define OPTION_NEWLINE_CRLF	(1<<2)
#define OPTION_NEWLINE_CRORLF	(OPTION_NEWLINE_CR|OPTION_NEWLINE_LF)
#define OPTION_NEWLINE_RAW	(1<<3)

/* Important options */
#define DUMP_FILENAME_PREFIX	"ssterm-dump-"
#define DUMP_MAX_FILES		100
#define DEFAULT_BUFFER_SIZE	4096

/******************************************************************************
 ******************************************************************************
 ******************************************************************************/

/* default serial port settings */
int tty_baudrate = 9600;
int tty_parity = PARITY_NONE;
int tty_databits = 8;
int tty_stopbits = 1;
int tty_flowcontrol = FLOW_CONTROL_NONE;
int tty_output_newline = OPTION_NEWLINE_RAW;
int tty_input_newline = OPTION_NEWLINE_LF;
int tty_buffer_size = DEFAULT_BUFFER_SIZE;

/******************************************************************************
 ******************************************************************************
 ******************************************************************************/

/* serial port file descriptor */
int tty_fd;

/* circular buffer data structure to hold tty data */
unsigned char *tty_buffer;
int tty_buffer_index_1;
int tty_buffer_index_2;
int tty_buffer_wrap;

/* read thread */
pthread_t read_thread;
/* signaling variable to read thread */
int read_thread_signal;

/* curses window and coordinates */
WINDOW *screen_pad;
/* screen viewport index of the curses pad */ 
int screen_pad_y;
/* curses max lines and cols saved from original measurement */
int screen_max_lines, screen_max_cols;
int stdout_cursor_x;
/* default color coded characters and colors */
char screen_color_coded_chars[] =  {'\r', '\n'};
short screen_color_coded_colors[] = {COLOR_MAGENTA, COLOR_CYAN};

/* options variable for different UI functionality */
int ui_options;

/******************************************************************************
 ******************************************************************************
 ******************************************************************************/

void handler_sigint(int signal);

int tty_open(const char *device, int options);
int tty_set_options(void);
int tty_read_circular(void);
int tty_read_regular(void);
int tty_write(unsigned char *data, int data_len);
void tty_buffer_clear(void);
int tty_buffer_dump(void);

int screen_init(void);
void screen_cleanup(void);
void screen_scroll_home(void);
void screen_scroll_end(void);
void screen_scroll_up(int lines);
void screen_scroll_down(int lines);
void screen_update(int index_1, int index_2);

void stdout_print(void);

void *read_curses_loop(void *id);
void write_curses_loop(void);

int read_write_stdin_loop(void);

static void printVersion(FILE *stream);
static void printCommands(FILE *stream);
static void printUsage(FILE *stream, const char *programName);
int main(int argc, char *argv[]);

/******************************************************************************
 *** SIGINT Handler / Clean Up                                              ***
 ******************************************************************************/

void handler_sigint(int signal) {
	/* Clean up curses */
	screen_cleanup();
	/* Tell our read thread to exit */
	read_thread_signal |= SIGNAL_RTH_EXIT;
	/* Join our read thread to this thread */
	pthread_join(read_thread, NULL);
	/* Make sure all of our pthreads have terminaed */
	pthread_exit(NULL);
	/* Close the serial port */
	close(tty_fd);
	/* Free our tty buffer */
	free(tty_buffer);
	/* Exit */
	exit(EXIT_SUCCESS);
}

/******************************************************************************
 *** Serial port options, read, write                                       ***
 ******************************************************************************/

int tty_open(const char *device, int options) {

	/* Open the serial port */
	tty_fd = open(device, options);
	if (tty_fd < 0)
		return ERROR_ERRNO;

	return 0;
}

int tty_set_options(void) {
	int retVal;
	struct termios options;
	speed_t new_baudrate;

	/* Grab the current options */
	retVal = tcgetattr(tty_fd, &options);
	if (retVal < 0)
		return ERROR_ERRNO;

	switch (tty_baudrate) {
		case 50: new_baudrate = B50; break;
		case 75: new_baudrate = B75; break;
		case 110: new_baudrate = B110; break;
		case 134: new_baudrate = B134; break;
		case 150: new_baudrate = B150; break;
		case 200: new_baudrate = B200; break;
		case 300: new_baudrate = B300; break;
		case 600: new_baudrate = B600; break;
		case 1200: new_baudrate = B1200; break;
		case 1800: new_baudrate = B1800; break;
		case 2400: new_baudrate = B2400; break;
		case 4800: new_baudrate = B4800; break;
		case 9600: new_baudrate = B9600; break;
		case 19200: new_baudrate = B19200; break;
		case 38400: new_baudrate = B38400; break;
		case 57600: new_baudrate = B57600; break;
		case 115200: new_baudrate = B115200; break;
		case 230400: new_baudrate = B230400; break;
		/* Baudrates B460800 and up removed due to the lack of these
		 * definitions in some *nix platforms. */
		default: return ERROR_BAUDRATE;
	}

	/* Clear cflag and set it from scratch */
	options.c_cflag = 0;
	
	/* Set the input and output baudrates */
	retVal = cfsetispeed(&options, new_baudrate);
	if (retVal < 0)
		return ERROR_BAUDRATE;
	retVal = cfsetospeed(&options, new_baudrate);
	if (retVal < 0)
		return ERROR_BAUDRATE;

	switch (tty_databits) {
		case 5: options.c_cflag |= CS5; break;
		case 6: options.c_cflag |= CS6; break;
		case 7: options.c_cflag |= CS7; break;
		case 8: options.c_cflag |= CS8; break;
		default: return ERROR_DATABITS;
	}

	switch (tty_parity) {
		case PARITY_NONE: break;
		case PARITY_EVEN: options.c_cflag |= PARENB; break;
		case PARITY_ODD: options.c_cflag |= (PARENB | PARODD); break;
		default: return ERROR_PARITY;
	}

	switch (tty_stopbits) {
		case 1: break;
		case 2: options.c_cflag |= CSTOPB; break;
		default: return ERROR_STOPBITS;
	}
	
	switch (tty_flowcontrol) {
		case FLOW_CONTROL_NONE: break;
		case FLOW_CONTROL_RTSCTS: options.c_cflag |= CRTSCTS; break;			/* We'll handle this later, in c_iflag */
		case FLOW_CONTROL_XONXOFF: break;
		default: return ERROR_FLOWCONTROL;
	}

	/* Enable the receiver */
	options.c_cflag |= (CREAD | CLOCAL);

	/* Turn off signals generated from special characters, turn of canonical
	 * mode so we can have raw input */
	//options.c_lflag &= ~(ISIG | ECHO | ICANON);
	options.c_lflag = 0;

	/* Turn off any POSIX defined output processing and character
	 * mapping/delays for pure raw output  */
	options.c_oflag = 0;

	/* Ignore break characters */
	options.c_iflag = IGNBRK;
	/* Enable parity checking and parity bit stripping if we are using 
	 * parity */
	if (tty_parity != PARITY_NONE)
		options.c_iflag |= (INPCK | ISTRIP);

	/* Turn on XON/XOFF if we want software flow control */
	if (tty_flowcontrol == FLOW_CONTROL_XONXOFF)
		options.c_iflag |= (IXON | IXOFF | IXANY);

	/* Set the new options of the serial port */
	retVal = tcsetattr(tty_fd, TCSANOW, &options);
	if (retVal < 0)
		return ERROR_ERRNO;

	return 0;
}

int tty_read_circular(void) {
	int retVal;

	/* Wrap around if we reach the end of the circular buffer */
	if (tty_buffer_index_2 == tty_buffer_size) {
		tty_buffer_index_2 = 0;
		tty_buffer_wrap = 1;
	}

	/* Catch up index 1 to index 2, now that we've processed the
	 * previously new data between index 1 and index 2 */
	tty_buffer_index_1 = tty_buffer_index_2;

	/* Read as much data as we can */
	retVal = read(tty_fd, tty_buffer+tty_buffer_index_1, tty_buffer_size-tty_buffer_index_2);
	if (retVal < 0 && errno != EWOULDBLOCK)
		return ERROR_ERRNO;
	
	/* If no data was returned because none was available */
	if (retVal < 0 && errno == EWOULDBLOCK)
		tty_buffer_index_2 += 0;
	else
	/* Otherwise increment our index 2 by the number of read characters */
		tty_buffer_index_2 += retVal;

	return 0;
}

int tty_read_regular(void) {
	int retVal;

	/* Read as much data as we can */
	retVal = read(tty_fd, tty_buffer, tty_buffer_size);
	if (retVal < 0 && errno != EWOULDBLOCK)
		return ERROR_ERRNO;

	/* If no data was returned because none was available */
	if (retVal < 0 && errno == EWOULDBLOCK)
		tty_buffer_index_1 = 0;
	else
	/* Otherwise set our index 1 by the number of read characters */
		tty_buffer_index_1 = retVal;

	return 0;
}

int tty_write(unsigned char *data, int data_len) {
	int retVal;

	retVal = write(tty_fd, data, data_len);
	if (retVal < 0)
		return ERROR_ERRNO;

	return 0;
}

void tty_buffer_clear(void) {
	int i;

	/* Zero out the buffer */
	for (i = 0; i < tty_buffer_size; i++)
		tty_buffer[i] = 0;

	/* Reset our circular buffer indexes and wrap indicator */
	tty_buffer_index_1 = tty_buffer_index_2 = 0;
	tty_buffer_wrap = 0;
}

int tty_buffer_dump(void) {
	char filename[sizeof(DUMP_FILENAME_PREFIX)+4];
	FILE *fp;
	int i;

	/* First find a non-existent suitable file to place the dump */
	for (i = 0; i < DUMP_MAX_FILES; i++) {
		sprintf(filename, "%s%02d", DUMP_FILENAME_PREFIX, i);
		if (access(filename, F_OK) != 0)
			break;
	}

	/* Error out if we've reached our max number of file dumps */
	if (i == DUMP_MAX_FILES)
		return -1;

	/* Open the file, error out if there was an error */
	fp = fopen(filename, "w");
	if (fp == NULL)
		return -1;

	/* Write the tty buffer to the file */

	/* If we've already wrapped around */
	if (tty_buffer_wrap) {
		/* Write from index 2 to the end of the buffer */
		if (fwrite(tty_buffer+tty_buffer_index_2, 1, tty_buffer_size-tty_buffer_index_2, fp) < (tty_buffer_size-tty_buffer_index_2))
			return -1;
		/* Write from the beginning of the buffer to index 1 */
		if (fwrite(tty_buffer, 1, tty_buffer_index_2, fp) < tty_buffer_index_2)
			return -1;
		
	} else {
		/* We haven't wrapped around yet, so just write from beginning
		 * of the buffer to index 2 */
		if (fwrite(tty_buffer, 1, tty_buffer_index_2, fp) < tty_buffer_index_2)
			return -1;
	}

	fclose(fp);

	return 0;
}

/******************************************************************************
 *** Curses Window Initialization and Printing                              ***
 ******************************************************************************/

int screen_init(void) {
	int i;

	/* Initialize the curses screen */
	initscr();
	noecho();
	raw();
	keypad(stdscr, TRUE);

	/* Enable echo if it is specified */
	if (ui_options & UI_OPTION_ECHO)
		echo();

	/* Create a new pad the user can scroll through the tty data with */
	getmaxyx(stdscr, screen_max_lines, screen_max_cols);
	screen_pad = newpad(tty_buffer_size, screen_max_cols);
	if (newpad == NULL)
		return ERROR_ERRNO;
		
	/* Initialize colors and the color pairs for the color coded characters,
	 * if they exist. */
	start_color();
	for (i = 0; i < sizeof(screen_color_coded_chars); i++) {
		init_pair(i+1, COLOR_BLACK, screen_color_coded_colors[i]);
	} 

	/* Reset our pad window of view */
	screen_pad_y = 0;

	return 0;
}

void screen_cleanup(void) {
	delwin(screen_pad);
	endwin();
}

void screen_scroll_home(void) {
	screen_pad_y = 0;
}

void screen_scroll_end(void) {
	int cursor_y, cursor_x;
	
	/* Bound the scroll down with at the end of the current cursor */
	getyx(screen_pad, cursor_y, cursor_x);
	screen_pad_y = cursor_y-screen_max_lines+1;
}

void screen_scroll_up(int lines) {
	/* Scroll our pad down, bottom out at 0 */
	screen_pad_y -= lines;
	if (screen_pad_y < 0)
		screen_pad_y = 0;
}

void screen_scroll_down(int lines) {
	int cursor_y, cursor_x;

	/* Scroll our pad up, bottom out at the current cursor position */
	screen_pad_y += lines;

	/* Bound the scroll down with at the end of the current cursor */
	getyx(screen_pad, cursor_y, cursor_x);
	if (screen_pad_y > cursor_y-screen_max_lines)
		screen_pad_y = cursor_y-screen_max_lines+1;
}

void screen_update(int index_1, int index_2) {
	int screen_index;
	int i = 0;
	int cursor_y, cursor_x;
	int found_cr = 0;

	/* Print the characters from specified index_1 to index_2 of the tty 
	 * buffer */
	for (screen_index = index_1; screen_index < index_2; screen_index++) {
		if (ui_options & UI_OPTION_HEX) {
			if (ui_options & UI_OPTION_COLOR_CODED) {
				/* Check if this character matches a color
				 * coded character */
				for (i = 0; i < sizeof(screen_color_coded_chars); i++) {
					/* If so, turn on its color pair */
					if (tty_buffer[screen_index] == (unsigned char)screen_color_coded_chars[i]) {
						wattron(screen_pad, COLOR_PAIR(i+1));
						break;
					}
				}
			}
			/* Write the character in hex */
			wprintw(screen_pad, "%02X", tty_buffer[screen_index]);

			/* Turn off the color pair if we turned it on for a
			 * color coded character. */
			if (i != sizeof(screen_color_coded_chars)) {
				wattroff(screen_pad, COLOR_PAIR(i+1));
				wattron(screen_pad, COLOR_PAIR(0));
			}

			if (ui_options & UI_OPTION_HEX_NEWLINE) {
			/* Print a newline if we encountered one, otherwise
			 * just a space to separate hex characters */
				if (tty_buffer[screen_index] == '\r') {
				/* If we need both CRLF, set a flag reminding
			 	 * us that we are still looking for LF */
					if (tty_input_newline & OPTION_NEWLINE_CRLF)
						found_cr = 1;
				/* If we just need CR, print a newline now */
					else if (tty_input_newline & OPTION_NEWLINE_CR) 
						waddch(screen_pad, '\n');
				} else if (tty_buffer[screen_index] == '\n') {
				/* If we need both CRLF, and we already found
			 	 * CR, go ahead and print the newline */
					if (tty_input_newline & OPTION_NEWLINE_CRLF) {
						if (found_cr) 
							waddch(screen_pad, '\n');
				/* If we just need LF, print a newline now */
					} else if (tty_input_newline & OPTION_NEWLINE_LF) {
						waddch(screen_pad, '\n');
					}
				} else {
				/* If we were looking for the LF to a CR,
				 * and we didn't come across it, clear our
				 * reminder. */
					found_cr = 0;
				}
			}

			/* Pretty print for hex characters */

			getyx(screen_pad, cursor_y, cursor_x);
			/* If we're getting near the edge of the screen, move
			 * over to the next line so all of our hex characters
			 * are aligned */
			if (cursor_x >= (screen_max_cols-2))
				waddch(screen_pad, '\n');
			/* Otherwise, just add a space between each hex */
			/* Make sure we didn't have a newline above carry us
			 * over before adding a space */
			else if (cursor_x != 0)
				waddch(screen_pad, ' ');

		} else {
			/* Special handling for newlines */
			if (tty_buffer[screen_index] == '\r' && !(tty_input_newline & OPTION_NEWLINE_RAW)) {
				/* If we need both CRLF, set a flag reminding
				 * us that we are still looking for LF */
				if (tty_input_newline & OPTION_NEWLINE_CRLF)
					found_cr = 1;
				/* If we just need CR, print a newline now */
				else if (tty_input_newline & OPTION_NEWLINE_CR)
					waddch(screen_pad, '\n');
			} else if (tty_buffer[screen_index] == '\n' && !(tty_input_newline & OPTION_NEWLINE_RAW)) {
				/* If we need both CRLF, and we already found
				 * CR, go ahead and print the newline */
				if (tty_input_newline & OPTION_NEWLINE_CRLF) {
					if (found_cr)
						waddch(screen_pad, '\n');
				/* If we just need LF, print a newline now */
				} else if (tty_input_newline & OPTION_NEWLINE_LF) {
					waddch(screen_pad, '\n');
				}
			} else {
				/* Print the normal character as usual */
				waddch(screen_pad, tty_buffer[screen_index]);
				/* If we were looking for the LF to a CR,
				 * and we didn't come across it, clear our
				 * reminder. */
				found_cr = 0;
			}
		}

		getyx(screen_pad, cursor_y, cursor_x);
		/* If we've reached the end of our pad, refresh the screen */
		if (cursor_y == tty_buffer_size-1) {
			read_thread_signal |= SIGNAL_RTH_SCREEN_REFRESH;
		} else {
			/* Only scroll down if we're looking at the end of the
			 * buffer */
			if (screen_pad_y >= (cursor_y-screen_max_lines-1)) {
				cursor_y -= screen_pad_y;
				/* Automatically scroll down if we get off of the pad */
				if (cursor_y >= (screen_max_lines-1))
					screen_pad_y += (cursor_y-screen_max_lines+1);
			}
		}
	}

	prefresh(screen_pad, screen_pad_y, 0, 0, 0, screen_max_lines-1, screen_max_cols);
}

/******************************************************************************
 *** stdout Printing                                                        ***
 ******************************************************************************/

void stdout_print(void) {
	int i;
	int found_cr = 0;

	for (i = 0; i < tty_buffer_index_1; i++) {
		if (ui_options & UI_OPTION_HEX) {
			/* Write the character in hex */
			printf("%02X", tty_buffer[i]);
			stdout_cursor_x += 3;

			if (ui_options & UI_OPTION_HEX_NEWLINE) {
			/* Print a newline if we encountered one, otherwise
			 * just a space to separate hex characters */
				if (tty_buffer[i] == '\r') {
				/* If we need both CRLF, set a flag reminding
				 * us that we are still looking for LF */
					if (tty_input_newline & OPTION_NEWLINE_CRLF)
						found_cr = 1;
				/* If we just need CR, print a newline now */
					else if (tty_input_newline & OPTION_NEWLINE_CR) {
						fputc('\n', stdout);
						stdout_cursor_x = 0;
					}
				} else if (tty_buffer[i] == '\n') {
				/* If we need both CRLF, and we already found
				 * CR, go ahead and print the newline */
					if (tty_input_newline & OPTION_NEWLINE_CRLF) {
						if (found_cr) {
							fputc('\n', stdout);
							stdout_cursor_x = 0;
						}
				/* If we just need LF, print a newline now */
					} else if (tty_input_newline & OPTION_NEWLINE_LF) {
						fputc('\n', stdout);
						stdout_cursor_x = 0;
					}
				} else {
				/* If we were looking for the LF to a CR,
				 * and we didn't come across it, clear our
				 * reminder. */
					found_cr = 0;
				}
			}	

			/* Pretty print for hex characters */

			/* If we're at the end of the screen, print a
			 * newline, otherwise just print a space between hex
			 * characters. */
			if (stdout_cursor_x >= (screen_max_cols-1)) {
				fputc('\n', stdout);
				stdout_cursor_x = 0;
			} else if (stdout_cursor_x != 0) {
				fputc(' ', stdout);
			}			
		} else {
			/* Special handling for newlines */
			if (tty_buffer[i] == '\r' && !(tty_input_newline & OPTION_NEWLINE_RAW)) {
				/* If we need both CRLF, set a flag reminding
				 * us that we are still looking for LF */
				if (tty_input_newline & OPTION_NEWLINE_CRLF)
					found_cr = 1;
				/* If we just need CR, print a newline now */
				else if (tty_input_newline & OPTION_NEWLINE_CR)
					fputc('\n', stdout);
			} else if (tty_buffer[i] == '\n' && !(tty_input_newline & OPTION_NEWLINE_RAW)) {
				/* If we need both CRLF, and we already found
				 * CR, go ahead and print the newline */
				if (tty_input_newline & OPTION_NEWLINE_CRLF) {
					if (found_cr)
						fputc('\n', stdout);
				/* If we just need LF, print a newline now */
				} else if (tty_input_newline & OPTION_NEWLINE_LF) {
					fputc('\n', stdout);
				}
			} else {
				/* Print the normal character as usual */
				fputc(tty_buffer[i], stdout);
				/* If we were looking for the LF to a CR,
				 * and we didn't come across it, clear our
				 * reminder. */
				found_cr = 0;
			}
		}
	}

	fflush(stdout);
}


/******************************************************************************
 *** Curses Read and Write Threads                                          ***
 ******************************************************************************/

void *read_curses_loop(void *id) {
	int retVal;
	fd_set rfds;
	struct timeval tv;

	read_thread_signal = 0;
	tty_buffer_clear();
	while (1) {
		/* If we need to exit */
		if (read_thread_signal & SIGNAL_RTH_EXIT)
			break;

		/* If the write thread wants us to clear the tty buffer */
		if (read_thread_signal & SIGNAL_RTH_BUFFER_CLEAR) {
			read_thread_signal &= ~SIGNAL_RTH_BUFFER_CLEAR;
			/* Clear the tty buffer */
			tty_buffer_clear();
			/* Clear the screen pad and reset our screen pad
			 * view port */
			wclear(screen_pad);
			screen_pad_y = 0;
		}

		/* If the write thread wants us to refresh the screen buffer */
		if (read_thread_signal & SIGNAL_RTH_SCREEN_REFRESH) {
			int cursor_y, cursor_x;

			read_thread_signal &= ~SIGNAL_RTH_SCREEN_REFRESH;
			/* Clear the screen pad and update our screen pad
			 * view port to the end of the printed tty buffer */
			wclear(screen_pad);
			/* If we've already wrapped around in the circular
			 * buffer */
			if (tty_buffer_wrap) {
				/* Redraw the old data: index 2 to the end
				 * of the buffer */
				screen_update(tty_buffer_index_2, tty_buffer_size);
				/* Redraw the new data: beginning of buffer
				 * up to index 2 */
				screen_update(0, tty_buffer_index_2);
			} else {
				/* Otherwise redraw the data we have in the
				 * buffer so far, beginning of buffer to index 2
				 */
				screen_update(0, tty_buffer_index_2);
			}	
			/* Adjust screen pad y to the "new end"
			 * This has to do with our screen pad actually
			 * being greater in size than the tty buffer
			 * itself, so the new end of our data has
			 * shortened. */
			getyx(screen_pad, cursor_y, cursor_x);
			if (screen_pad_y > cursor_y-screen_max_lines)
				screen_pad_y = cursor_y-screen_max_lines+1;

			continue;
		}

		/* If the write thread wants us to dump the tty buffer */
		if (read_thread_signal & SIGNAL_RTH_BUFFER_DUMP) {
			read_thread_signal &= ~SIGNAL_RTH_BUFFER_DUMP;
			/* Dump the file */
			retVal = tty_buffer_dump();
			/* If we had an error, complain, and refresh the screen
			 * buffer. */
			if (retVal < 0) {
				/* Highlight the error message */
				attron(A_STANDOUT);
				printw("Error dumping tty buffer to file!\n");
				attroff(A_STANDOUT);
				refresh();
				sleep(1);
				/* Refresh the screen buffer to get rid of the
				 * above error message */
				read_thread_signal |= SIGNAL_RTH_SCREEN_REFRESH;
				continue;
			}
		}

		/* Just update the screen with the new data */
		screen_update(tty_buffer_index_1, tty_buffer_index_2);

		/* Catch up the tty buffer index 1 to index 2 now that we have
		 * updated the screen with the new data */	
		tty_buffer_index_1 = tty_buffer_index_2;

		/* Clear our file descriptor list and add our tty fd */
		FD_ZERO(&rfds);
		FD_SET(tty_fd, &rfds);

		/* Set a 10000 microsecond timeout */
		tv.tv_sec = 0;
		tv.tv_usec = 10000;

		/* Check if tty fd has data */
		retVal = select(tty_fd+1, &rfds, NULL, NULL, &tv);
		if (retVal == -1) {
			perror("Error select() with serial port");
			handler_sigint(SIGINT);
		}

		if (retVal > 0) {
			/* Read in new data from the serial port */
			if (tty_read_circular() < 0) {
				perror("Error reading");
				handler_sigint(SIGINT);
			}
		}
	}

	return NULL;	
}

void write_curses_loop(void) {
	int ch;
	unsigned char crlf[2] = {'\r', '\n'};

	while (1) {
		ch = wgetch(stdscr);
		/* Check for special control keys */
		if (ch == KEY_UP) {
			screen_scroll_up(1);
		} else if (ch == KEY_HOME) {
			screen_scroll_home();
		} else if (ch == KEY_END) {
			screen_scroll_end();
		} else if (ch == KEY_DOWN) {
			screen_scroll_down(1);
		} else if (ch == KEY_PPAGE) {
			screen_scroll_up(5);
		} else if (ch == KEY_NPAGE) {
			screen_scroll_down(5);
		} else if (ch == CTRL_C) {
			handler_sigint(SIGINT);
		} else if (ch == CTRL_H) {
			/* Toggle the screen hex mode */
			if (ui_options & UI_OPTION_HEX)
				ui_options &= ~UI_OPTION_HEX;
			else
				ui_options |= UI_OPTION_HEX;
		} else if (ch == CTRL_N) {
			/* Toggle interpretation of newlines in hex mode */
			if (ui_options & UI_OPTION_HEX_NEWLINE)
				ui_options &= ~UI_OPTION_HEX_NEWLINE;
			else
				ui_options |= UI_OPTION_HEX_NEWLINE;
		} else if (ch == CTRL_O) {
			/* Toggle the screen color coding mode */
			if (ui_options & UI_OPTION_COLOR_CODED)
				ui_options &= ~UI_OPTION_COLOR_CODED;
			else
				ui_options |= UI_OPTION_COLOR_CODED;
		} else if (ch == CTRL_L) {
			/* Signal to our read thread to clear the tty buffer */
			read_thread_signal |= SIGNAL_RTH_BUFFER_CLEAR;
		} else if (ch == CTRL_R) {
			/* Signal to our read thread to refresh the screen
			 * buffer. */
			read_thread_signal |= SIGNAL_RTH_SCREEN_REFRESH;
		} else if (ch == CTRL_D) {
			/* Signal to our read thread to dump the tty buffer */
			read_thread_signal |= SIGNAL_RTH_BUFFER_DUMP;
		} else {
			/* Otherwise, write out the terminal */
			
			/* If we encountered a newline character */
			if (ch == '\n') {
				/* Send CRLF if we are outputting CRLF and
				 * start back up top. */
				if (tty_output_newline & OPTION_NEWLINE_CRLF) {
					tty_write(crlf, sizeof(crlf));
					continue;
				/* Change to CR if we are just outputting CR */
				} else if (tty_output_newline & OPTION_NEWLINE_CR) {
					ch = '\r';
				/* Ignore this character if we are not 
				 * transmitting newlines. */
				} else if (tty_output_newline & OPTION_NEWLINE_NONE) {
					continue;
				}
			}	
			tty_write((unsigned char *)&ch, 1);
		}
	}		
}

/******************************************************************************
 *** stdin/stdout Read/Write select() based loop                            ***
 ******************************************************************************/

int read_write_stdin_loop(void) {
	fd_set rfds;
	int retVal;
	int stdin_ch;
	unsigned char crlf[2] = {'\r', '\n'};
	struct termios options;
	struct winsize win;

	/* Get the console window size */
	if (ioctl(0, TIOCGWINSZ, &win) < 0) {
		perror("Error getting console window size");
		return ERROR_ERRNO;
	}
	screen_max_cols = win.ws_col;

	/* Get the stdin tty options */
	if (tcgetattr(0, &options) < 0) {
		perror("Error getting stdin tty options");
		return ERROR_ERRNO;
	}
	/* Disable canonical input and echo, so we can send characters without
	 * the need of a line feed */
	options.c_lflag &= ~(ICANON | ECHO | ECHOE);
	/* Turn off support for XON & XOFF characters so they pass through */
	options.c_iflag &= ~(IXON | IXOFF | IXANY);
	/* Enable echo if it is specified */
	if (ui_options & UI_OPTION_ECHO)
		options.c_lflag |= ECHO;
	/* Set the stdin tty options */
	if (tcsetattr(0, TCSANOW, &options) < 0) {
		perror("Error setting stdin tty options");
		return ERROR_ERRNO;
	}

	while (1) {
		/* Clear our file descriptor list */
		FD_ZERO(&rfds);
		/* Add stdin and our tty fd to our file descriptor list */
		FD_SET(0, &rfds);
		FD_SET(tty_fd, &rfds);

		/* Check if stdin or our tty fd has data */
		retVal = select(tty_fd+1, &rfds, NULL, NULL, NULL);
		if (retVal == -1) {
			perror("Error select() with stdin and serial port");
			return ERROR_ERRNO;
		}

		if (FD_ISSET(0, &rfds)) {
			stdin_ch = fgetc(stdin);
			if (stdin_ch == '\n') {
				/* Write CRLF if we are outputting CRLF */
				if (tty_output_newline & OPTION_NEWLINE_CRLF) {
					tty_write(crlf, sizeof(crlf));
				/* Change to CR if we are just outputting CR */
				} else if (tty_output_newline & OPTION_NEWLINE_CR) {
					stdin_ch = '\r';
					tty_write((unsigned char *)&stdin_ch, 1);
				/* Ignore this character if we are not
				 * transmitting newlines */
				} else if (tty_output_newline & OPTION_NEWLINE_NONE) {
					;
				/* Otherwise, just print the \n as usual */
				} else {
					tty_write((unsigned char *)&stdin_ch, 1);
				}
			} else {
				tty_write((unsigned char *)&stdin_ch, 1);
			}
		}

		if (FD_ISSET(tty_fd, &rfds)) {
			/* Read from the serial port */	
			retVal = tty_read_regular();
			if (retVal < 0) {
				perror("Error reading");
				return ERROR_ERRNO;
			}

			/* Print if we received data */
			if (tty_buffer_index_1 > 0) {
				stdout_print();
			}
		}
	}

	return 0;
}

/******************************************************************************
 *** Command-Line Options Parsing                                           ***
 ******************************************************************************/

static struct option long_options[] = {
	/* Interface Options */
	{"stdin", no_argument, NULL, 's'},
	/* Serial Port Options */
	{"baudrate", required_argument, NULL, 'b'},
	{"databits", required_argument, NULL, 'd'},
	{"parity", required_argument, NULL, 'p'},
	{"stopbits", required_argument, NULL, 't'},
	{"flowcontrol", required_argument, NULL, 'f'},
	{"tx-nl", required_argument, NULL, 0},
	{"rx-nl", required_argument, NULL, 0},
	{"buffer-size", required_argument, NULL, 0},
	/* Formatting Options */
	{"echo", no_argument, NULL, 'e'},
	{"hex", no_argument, NULL, 'x'},
	{"hex-nl", no_argument, NULL, 0},
	/* Curses Formatting Options */
	{"rx-nl-color", no_argument, NULL, 'c'}, 
	/* Misc. Options */
	{"help", no_argument, NULL, 'h'},
	{"commands", no_argument, NULL, 'k'},
	{"version", no_argument, NULL, 'v'},
	{NULL, 0, NULL, 0}
};

static void printVersion(FILE *stream) {
	fprintf(stream, "ssterm version 1.0 - 2009/10/23\n");
	fprintf(stream, "Written by Vanya Sergeev - <vsergeev@gmail.com>\n");
}
	
static void printCommands(FILE *stream) {
	fprintf(stream, "\n\
Curses Commands for ssterm:\n\
 Page Up/Page Down	Scroll buffer up/down by 5 lines\n\
 Home/End		Scroll to the top/bottom of the buffer\n\
 Up/Down		Scroll buffer up/down by 1 line\n\
\n\
 Ctrl-l			Clear buffer\n\
 Ctrl-r			Reprint buffer\n\
 Ctrl-d			Dump buffer to file\n\
\n\
 Ctrl-h			Hexadecimal representation mode\n\
 Ctrl-n			Interpret newlines in hexadecimal mode\n\
 Ctrl-o			Color-code newline characters in hexadecimal\n\
			mode\n\
\n\
 Ctrl-q			Send XON\n\
 Ctrl-s			Send XOFF\n\
\n");
}

static void printUsage(FILE *stream, const char *programName) {
	fprintf(stream, "Usage: %s <option(s)> <serial port>\n", programName);
	fprintf(stream, " ssterm - simple serial-port terminal\n");
	fprintf(stream, " Written by Vanya A. Sergeev - <vsergeev@gmail.com>.\n\n");
	fprintf(stream, "\
 Interface Options:\n\
  -s, --stdin			Use an stdin/stdout interface as opposed to \n\
				curses \n\
\n\
 Serial Port Options:\n\
  -b, --baudrate <rate>		Specify the baudrate\n\
  -d, --databits <number>	Specify the number of data bits [5,6,7,8]\n\
  -p, --parity <type>	 	Specify the parity [none, odd, even]\n\
  -t, --stopbits <number>	Specify number of stop bits [1,2]\n\
  -f, --flow-control <type>	Specify the flow-control [none, rtscts, xonxoff]\n\
\n\
 Formatting Options:\n\
  --tx-nl <combination>		Specify the transmit newline combination\n\
				 [raw, none, cr, lf, crlf, crorlf]\n\
  --rx-nl <combination>		Specify the receive newline combination\n\
				 [raw, none, cr, lf, crlf, crorlf]\n\
  -e, --echo			Turn on local character echo\n\
  -x, --hex			Turn on hexadecimal representation mode\n\
  --hex-nl			Turn on newlines in hexadecimal mode\n\
\n\
 Curses Formatting Options:\n\
  -c, --rx-nl-color		Color-code all receive newline combinations\n\
\n\
 Misc. Options:\n\
  --buffer-size <bytes>		Specify the size of ssterm's receive buffer\n\
  -h, --help			Display this usage/help\n\
  -k, --commands		Display curses commands\n\
  -v, --version			Display the program's version\n\n");
	fprintf(stream, "\
Default options: curses, 9600 8N1, flow control: none, transmit newline: raw,\n\
receive newline: LF, echo: off, hexadecimal: off, receive color-code: off,\n\
buffer size: 4096\n");
	fprintf(stream, "\n");
}

/******************************************************************************
 ******************************************************************************
 ******************************************************************************/

int main(int argc, char *argv[]) {
	int optc, long_index;
	int retVal;

	ui_options = 0;

	while (1) {
		int *var;
		optc = getopt_long(argc, (char * const *)argv, "b:d:p:t:f:scxehkv", long_options, &long_index);
		if (optc == -1)
			break;
		
		#define str_option_cmp(str) (strcasecmp(optarg, str) == 0)
		switch (optc) {
			/* Long option */
			case 0:
				/* --tx-nl */
				if (strcmp(long_options[long_index].name, "buffer-size") == 0) {
					tty_buffer_size = atoi(optarg);
					break;
				} else if (strcmp(long_options[long_index].name, "tx-nl") == 0) {
					var = &tty_output_newline;
				/* --rx-nl */
				} else if (strcmp(long_options[long_index].name, "rx-nl") == 0) {
					var = &tty_input_newline;
				/* --hex-nl */
				} else if (strcmp(long_options[long_index].name, "hex-nl") == 0) {
					ui_options |= UI_OPTION_HEX_NEWLINE;
					break;
				} else {
					break;
				}

				if (str_option_cmp(NEWLINE_NONE_STR))
					(*var) = OPTION_NEWLINE_NONE;
				else if (str_option_cmp(NEWLINE_CR_STR))
					(*var) = OPTION_NEWLINE_CR;
				else if (str_option_cmp(NEWLINE_LF_STR))
					(*var) = OPTION_NEWLINE_LF;
				else if (str_option_cmp(NEWLINE_CRLF_STR))
					(*var) = OPTION_NEWLINE_CRLF;
				else if (str_option_cmp(NEWLINE_CRORLF_STR))
					(*var) = OPTION_NEWLINE_CRORLF;
				else if (str_option_cmp(NEWLINE_RAW_STR))
					(*var) = OPTION_NEWLINE_RAW;
				break;
			case 's':
				ui_options |= UI_OPTION_STDIN_STDOUT;
				break;
			case 'b':
				tty_baudrate = atoi(optarg);
				break;
			case 'd':
				tty_databits = atoi(optarg);
				break;
			case 't':
				tty_stopbits = atoi(optarg);
				break;
			case 'p':
				if (str_option_cmp(PARITY_NONE_STR))
					tty_parity = PARITY_NONE;
				else if (str_option_cmp(PARITY_ODD_STR))
					tty_parity = PARITY_ODD;
				else if (str_option_cmp(PARITY_EVEN_STR))
					tty_parity = PARITY_EVEN;
				else
					tty_parity = -1;
				break;
			case 'f':
				if (str_option_cmp(FLOW_CONTROL_NONE_STR))
					tty_flowcontrol = FLOW_CONTROL_NONE;
				else if (str_option_cmp(FLOW_CONTROL_RTSCTS_STR))
					tty_flowcontrol = FLOW_CONTROL_RTSCTS;
				else if (str_option_cmp(FLOW_CONTROL_XONXOFF_STR))
					tty_flowcontrol = FLOW_CONTROL_XONXOFF;
				else
					tty_flowcontrol = -1;
				break;
			case 'e':
				ui_options |= UI_OPTION_ECHO;
				break;
			case 'x':
				ui_options |= UI_OPTION_HEX;
				break;
			case 'c':
				ui_options |= UI_OPTION_COLOR_CODED;
				break;
			case 'h':
				printUsage(stderr, argv[0]);
				exit(EXIT_SUCCESS);
			case 'k':
				printCommands(stderr);
				exit(EXIT_SUCCESS);
			case 'v':
				printVersion(stderr);
				exit(EXIT_SUCCESS);
			default:
				printUsage(stderr, argv[0]);
				exit(EXIT_SUCCESS);
		}
	}

	/* Check arguments */
	if (optind == argc) {
		printUsage(stderr, argv[0]);
		exit(EXIT_FAILURE);
	}
	
	if (!(ui_options & UI_OPTION_STDIN_STDOUT) && (tty_input_newline & OPTION_NEWLINE_RAW)) {
		fprintf(stderr, "Error: receive newline character option 'raw' unsupported in curses mode (CR characters will delete lines).\n");
		exit(EXIT_FAILURE);
	}

	/* Check supplied buffer size */
	if (tty_buffer_size < 0) {
		fprintf(stderr, "Invalid buffer size!\n");
		exit(EXIT_FAILURE);
	}

	/* Open the serial port in read-write, nonblocking, and not as a
	 * controlling terminal. */
	retVal = tty_open(argv[optind], O_RDWR | O_NOCTTY | O_NONBLOCK);
	if (retVal < 0) {	
		perror("Error opening serial port");
		exit(EXIT_FAILURE);
	}

	/* Set the serial port options */
	retVal = tty_set_options();
	switch (retVal) {
		case ERROR_ERRNO:
			perror("Error setting serial port options");
			break;
		case ERROR_BAUDRATE:
			fprintf(stderr, "Invalid baudrate setting!\n");
			break;
		case ERROR_DATABITS:
			fprintf(stderr, "Invalid data bits setting!\n");
			break;
		case ERROR_STOPBITS:
			fprintf(stderr, "Invalid stop bits setting!\n");
			break;
		case ERROR_PARITY:
			fprintf(stderr, "Invalid parity setting!\n");
			break;
		case ERROR_FLOWCONTROL:
			fprintf(stderr, "Invalid flow control setting!\n");
			break;
	}

	/* Check for setting errors, and quit if there were any */
	if (retVal < 0) {
		close(tty_fd);
		exit(EXIT_FAILURE);
	}

	/* Allocate memory for the tty_buffer */
	tty_buffer = malloc(tty_buffer_size * sizeof(char));
	if (tty_buffer == NULL) {
		perror("Error allocating memory for receive buffer");
		exit(EXIT_FAILURE);
	}

	if (!(ui_options & UI_OPTION_STDIN_STDOUT)) {
		/* Establish a handler for SIGINT since we're going into curses mode */
		signal(SIGINT, handler_sigint);

		/* Initialize our curses screen */
		retVal = screen_init();
		if (retVal < 0) {
			screen_cleanup();
			free(tty_buffer);
			close(tty_fd);
			perror("Error creating curses screen");
			exit(EXIT_FAILURE);
		}

		/* Thread our read and write loops */
		retVal = pthread_create(&read_thread, NULL, read_curses_loop, NULL);
		if (retVal < 0) {
			screen_cleanup();
			free(tty_buffer);
			close(tty_fd);
			perror("Error creating read pthread:");
			exit(EXIT_FAILURE);
		}
		/* This thread will take the write / UI loop */
		write_curses_loop();
	} else {
		/* Otherwise, enter the select() based read/write loop
		 * for stdin/stdout */
		retVal = read_write_stdin_loop();
	}

	return retVal;
}

