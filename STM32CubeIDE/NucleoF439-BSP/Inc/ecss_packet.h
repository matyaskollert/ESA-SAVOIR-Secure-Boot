/*
 * ecss_packet.h
 *
 * ECSS-inspired packet protocol — header definitions and API.
 *
 * The protocol uses a compact 7-byte primary header followed by a variable-
 * length data field.  All multi-byte fields in the on-wire format are
 * big-endian; the API converts them to/from the host (little-endian ARM)
 * representation automatically.
 *
 * Wire format (7 bytes, packed):
 *   [0]    version_type_flags  — Version(3) | Type(1) | Reserved(4)
 *   [1]    service_type        — one of PacketServiceType
 *   [2:3]  sequence_count      — big-endian 16-bit counter
 *   [4:5]  data_length         — big-endian payload byte count
 *   [6]    header_checksum     — XOR of bytes [0..5]
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#ifndef INC_ECSS_PACKET_H_
#define INC_ECSS_PACKET_H_

#include "stm32f4xx_hal.h"

/* =========================================================================
 * Service type identifiers
 * ========================================================================= */
typedef enum
{
	PKT_START_UPLOAD = 0x01, /* Begin an image upload session              */
	PKT_DATA_CHUNK   = 0x02, /* Carry a chunk of image data                */
	PKT_END_UPLOAD   = 0x03, /* Signal end of image data stream            */
	PKT_DEBUG_LOG    = 0x04, /* Carry a human-readable debug string        */
	PKT_REPORT_DATA  = 0x05, /* Carry a serialised BSW boot-event report   */
	PKT_ACK          = 0x06, /* Positive acknowledgement                   */
	PKT_NACK         = 0x15, /* Negative acknowledgement (with error code) */
} PacketServiceType;

/* =========================================================================
 * Packet header structure (7 bytes, tightly packed)
 *
 * Stored and transmitted in network byte order (big-endian) for sequence_count
 * and data_length; ecss_parse_header() and ecss_pack_header() perform the
 * necessary byte-swap so that all other code works in host byte order.
 * ========================================================================= */
typedef struct __attribute__((packed))
{
	uint8_t version_type_flags; /* Version(3) | Type(1) | Reserved(4)        */
	uint8_t service_type;       /* PacketServiceType — command / telemetry id */
	uint16_t sequence_count;    /* Packet sequence number (big-endian)        */
	uint16_t data_length;       /* Payload byte count   (big-endian)          */
	uint8_t header_checksum;    /* XOR of header bytes [0..5]                 */
} ECSSPacketHeader;

/* =========================================================================
 * Constants
 * ========================================================================= */
#define ECSS_HEADER_SIZE 7 /* Byte length of ECSSPacketHeader on the wire */
#define ECSS_VERSION 0b001
#define ECSS_TYPE_TELECOMMAND 1
#define ECSS_TYPE_TELEMETRY 0

/* Helper macros for big-endian ↔ host byte-order conversion */
#define HTONS(x) ((uint16_t)((((x) & 0xFF) << 8) | (((x) >> 8) & 0xFF)))
#define NTOHS(x) HTONS(x)

/* =========================================================================
 * API
 * ========================================================================= */

/**
 * Compute the XOR checksum over the first 6 bytes of @p header.
 *
 * @param header  Populated header struct (header_checksum field is ignored).
 * @return        Computed checksum byte.
 */
uint8_t ecss_calculate_header_checksum(const ECSSPacketHeader* header);

/**
 * Verify the checksum stored in @p header against the computed value.
 *
 * @param header  Header to check (all fields including header_checksum).
 * @return        1 if the checksum is valid, 0 if it does not match.
 */
uint8_t ecss_verify_header_checksum(const ECSSPacketHeader* header);

/**
 * Deserialise a 7-byte wire buffer into @p header and validate the checksum.
 * Multi-byte fields (sequence_count, data_length) are converted from
 * network byte order to host byte order.
 *
 * @param buffer  Source byte array (at least ECSS_HEADER_SIZE bytes).
 * @param header  Destination struct; populated on success.
 * @return         0 on success, -1 if the header checksum is invalid.
 */
int8_t ecss_parse_header(const uint8_t* buffer, ECSSPacketHeader* header);

/**
 * Populate @p header with the given fields.  The checksum is intentionally
 * left at 0 and is computed only during ecss_pack_header().
 *
 * @param header          Destination struct.
 * @param service_type    One of PacketServiceType.
 * @param sequence_count  Monotonically increasing packet counter (host order).
 * @param data_length     Number of payload bytes that will follow (host order).
 * @param is_telecommand  1 for TC (uplink), 0 for TM (downlink).
 */
void ecss_create_header(ECSSPacketHeader* header, uint8_t service_type, uint16_t sequence_count,
                        uint16_t data_length, uint8_t is_telecommand);

/**
 * Serialise @p header into a 7-byte wire buffer and compute the checksum.
 * Multi-byte fields are converted to network byte order.
 *
 * @param header  Source header (host byte order; checksum is computed fresh).
 * @param buffer  Destination byte array (at least ECSS_HEADER_SIZE bytes).
 */
void ecss_pack_header(const ECSSPacketHeader* header, uint8_t* buffer);

#endif /* INC_ECSS_PACKET_H_ */
