/*
 * ecss_packet.h
 *
 * ECSS-inspired packet protocol implementation
 * Simplified version for proof of concept
 */

#ifndef INC_ECSS_PACKET_H_
#define INC_ECSS_PACKET_H_

#include "stm32f4xx_hal.h"

/* ECSS-inspired packet service types */
typedef enum {
    PKT_START_UPLOAD = 0x01,
    PKT_DATA_CHUNK = 0x02,
    PKT_END_UPLOAD = 0x03,
    PKT_DEBUG_LOG = 0x04,
    PKT_ACK = 0x06,
    PKT_NACK = 0x15
} PacketServiceType;

/* ECSS packet header structure
 * Primary Header (7 bytes):
 * - Version/Type/Flags (1 byte): Version(3 bits) | Type(1 bit) | Reserved(4 bits)
 * - Service Type (1 byte): Command type (START, DATA, END, ACK, NACK)
 * - Sequence Count (2 bytes, big-endian): Packet sequence number
 * - Data Length (2 bytes, big-endian): Length of data field
 * - Header Checksum (1 byte): XOR checksum of first 6 header bytes
 */
typedef struct __attribute__((packed)) {
    uint8_t version_type_flags;  // Version(3) | Type(1) | Reserved(4)
    uint8_t service_type;         // Service type (START, DATA, END, ACK, NACK)
    uint16_t sequence_count;      // Packet sequence number (big-endian)
    uint16_t data_length;         // Length of data field (big-endian)
    uint8_t header_checksum;      // XOR checksum of first 6 bytes
} ECSSPacketHeader;

#define ECSS_HEADER_SIZE 7
#define ECSS_VERSION 0b001
#define ECSS_TYPE_TELECOMMAND 1
#define ECSS_TYPE_TELEMETRY 0

/* Helper macros for byte order conversion */
#define HTONS(x) ((uint16_t)((((x) & 0xFF) << 8) | (((x) >> 8) & 0xFF)))
#define NTOHS(x) HTONS(x)


uint8_t ecss_calculate_header_checksum(const ECSSPacketHeader* header);

uint8_t ecss_verify_header_checksum(const ECSSPacketHeader* header);

int8_t ecss_parse_header(const uint8_t* buffer, ECSSPacketHeader* header);

void ecss_create_header(ECSSPacketHeader* header, 
                        uint8_t service_type,
                        uint16_t sequence_count,
                        uint16_t data_length,
                        uint8_t is_telecommand);

void ecss_pack_header(const ECSSPacketHeader* header, uint8_t* buffer);

#endif /* INC_ECSS_PACKET_H_ */
