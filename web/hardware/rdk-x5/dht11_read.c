#include <errno.h>
#include <gpiod.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_CHIP_PATH "/dev/gpiochip4"
#define DEFAULT_LINE_OFFSET 1
#define MAX_PULSES 140

struct pulse {
    int level;
    unsigned int width_us;
};

struct reading {
    unsigned char bytes[5];
    int start;
    int threshold;
};

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000ULL + ts.tv_nsec / 1000ULL;
}

static void busy_us(unsigned int us) {
    uint64_t end = now_us() + us;
    while (now_us() < end) {
    }
}

static int request_input(struct gpiod_line *line) {
    return gpiod_line_request_input(line, "dht11-read");
}

static int request_output(struct gpiod_line *line, int value) {
    return gpiod_line_request_output(line, "dht11-read", value);
}

static int capture_once(struct gpiod_line *line, struct pulse *pulses, int *pulse_count) {
    if (request_output(line, 1) < 0) {
        fprintf(stderr, "request output failed: %s\n", strerror(errno));
        return -1;
    }

    usleep(1200000);
    gpiod_line_set_value(line, 0);
    usleep(25000);
    gpiod_line_set_value(line, 1);
    busy_us(35);
    gpiod_line_release(line);

    if (request_input(line) < 0) {
        fprintf(stderr, "request input failed: %s\n", strerror(errno));
        return -1;
    }

    int n = 0;
    int last = gpiod_line_get_value(line);
    if (last < 0) {
        fprintf(stderr, "read line failed: %s\n", strerror(errno));
        gpiod_line_release(line);
        return -1;
    }

    uint64_t start = now_us();
    uint64_t last_t = start;
    uint64_t no_change_since = start;

    while (now_us() - start < 12000 && n < MAX_PULSES) {
        int v = gpiod_line_get_value(line);
        uint64_t t = now_us();
        if (v < 0) {
            fprintf(stderr, "read line failed: %s\n", strerror(errno));
            gpiod_line_release(line);
            return -1;
        }
        if (v != last) {
            pulses[n].level = last;
            pulses[n].width_us = (unsigned int)(t - last_t);
            n++;
            last = v;
            last_t = t;
            no_change_since = t;
        } else if (t - no_change_since > 5000 && n > 8) {
            break;
        }
    }

    if (n < MAX_PULSES) {
        pulses[n].level = last;
        pulses[n].width_us = (unsigned int)(now_us() - last_t);
        n++;
    }

    gpiod_line_release(line);
    *pulse_count = n;
    return 0;
}

static int decode(const struct pulse *pulses, int pulse_count, struct reading *out) {
    unsigned int highs[MAX_PULSES];
    int high_count = 0;

    for (int i = 0; i < pulse_count && high_count < MAX_PULSES; i++) {
        if (pulses[i].level == 1 && pulses[i].width_us < 1000) {
            highs[high_count++] = pulses[i].width_us;
        }
    }

    for (int start = 0; start < 8; start++) {
        if (start + 40 > high_count) continue;
        for (int threshold = 35; threshold <= 65; threshold += 5) {
            unsigned char b[5] = {0, 0, 0, 0, 0};
            for (int i = 0; i < 40; i++) {
                int bit = highs[start + i] > (unsigned int)threshold ? 1 : 0;
                b[i / 8] = (unsigned char)((b[i / 8] << 1) | bit);
            }

            int checksum_ok = (((b[0] + b[1] + b[2] + b[3]) & 0xff) == b[4]);
            int plausible = b[0] <= 100 && b[2] <= 60;
            if (checksum_ok && plausible) {
                memcpy(out->bytes, b, sizeof(b));
                out->start = start;
                out->threshold = threshold;
                return 0;
            }
        }
    }

    return -1;
}

static void print_usage(const char *argv0) {
    fprintf(stderr,
            "Usage: %s [--attempts N] [--json] [--debug]\n"
            "Default target: RDK X5 physical pin 11, /dev/gpiochip4 line 1.\n",
            argv0);
}

int main(int argc, char **argv) {
    int attempts = 12;
    int json = 0;
    int debug = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--json") == 0) {
            json = 1;
        } else if (strcmp(argv[i], "--debug") == 0) {
            debug = 1;
        } else if (strcmp(argv[i], "--attempts") == 0 && i + 1 < argc) {
            attempts = atoi(argv[++i]);
            if (attempts < 1) attempts = 1;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        } else {
            print_usage(argv[0]);
            return 2;
        }
    }

    struct gpiod_chip *chip = gpiod_chip_open(DEFAULT_CHIP_PATH);
    if (!chip) {
        fprintf(stderr, "open %s failed: %s\n", DEFAULT_CHIP_PATH, strerror(errno));
        return 2;
    }

    struct gpiod_line *line = gpiod_chip_get_line(chip, DEFAULT_LINE_OFFSET);
    if (!line) {
        fprintf(stderr, "get line offset %d failed: %s\n", DEFAULT_LINE_OFFSET, strerror(errno));
        gpiod_chip_close(chip);
        return 2;
    }

    for (int attempt = 1; attempt <= attempts; attempt++) {
        struct pulse pulses[MAX_PULSES];
        int pulse_count = 0;
        struct reading r;

        if (capture_once(line, pulses, &pulse_count) < 0) {
            gpiod_chip_close(chip);
            return 2;
        }

        if (decode(pulses, pulse_count, &r) == 0) {
            double humidity = r.bytes[0] + r.bytes[1] / 10.0;
            double temperature = r.bytes[2] + r.bytes[3] / 10.0;
            if (json) {
                printf("{\"ok\":true,\"humidity\":%.1f,\"temperature\":%.1f,"
                       "\"raw\":[%u,%u,%u,%u,%u],\"attempt\":%d,"
                       "\"start\":%d,\"threshold\":%d}\n",
                       humidity, temperature,
                       r.bytes[0], r.bytes[1], r.bytes[2], r.bytes[3], r.bytes[4],
                       attempt, r.start, r.threshold);
            } else {
                printf("OK humidity=%.1f%%RH temperature=%.1fC raw=[%u,%u,%u,%u,%u] attempt=%d\n",
                       humidity, temperature,
                       r.bytes[0], r.bytes[1], r.bytes[2], r.bytes[3], r.bytes[4],
                       attempt);
            }
            gpiod_chip_close(chip);
            return 0;
        }

        if (debug) {
            fprintf(stderr, "attempt %d: no valid checksum, pulses=%d\n", attempt, pulse_count);
        }
        usleep(2200000);
    }

    if (json) {
        printf("{\"ok\":false,\"error\":\"no valid DHT11 checksum\"}\n");
    } else {
        printf("FAIL no valid DHT11 checksum after %d attempts\n", attempts);
    }

    gpiod_chip_close(chip);
    return 1;
}
