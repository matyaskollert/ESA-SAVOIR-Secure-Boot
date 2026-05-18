/*
 * ecss_packet.c
 *
 * ECSS-inspired packet protocol — serialisation, deserialisation and
 * checksum functions.
 *
 * All public functions are declared in ecss_packet.h.  Internal helpers
 * are static and not exposed to callers.
 *
 *  Created on: Feb 2, 2026
 *      Author: Matyas
 */

#include "ecss_packet.h"
#include <string.h>

uint8_t ecss_calculate_header_checksum(const ECSSPacketHeader* header)
{
	const uint8_t* bytes = (const uint8_t*)header;
	uint8_t checksum     = 0;

	// XOR first 6 bytes (excluding checksum itself)
	for (int i = 0; i < 6; i++)
	{
		checksum ^= bytes[i];
	}

	return checksum;
}

uint8_t ecss_verify_header_checksum(const ECSSPacketHeader* header)
{
	uint8_t calculated = ecss_calculate_header_checksum(header);
	if (calculated == header->header_checksum)
	{
		return 1;
	}
	return 0;
}

int8_t ecss_parse_header(const uint8_t* buffer, ECSSPacketHeader* header)
{
	// Copy header bytes
	memcpy(header, buffer, ECSS_HEADER_SIZE);

	// Convert from network byte order (big-endian) to host
	header->sequence_count = NTOHS(header->sequence_count);
	header->data_length    = NTOHS(header->data_length);

	// Verify checksum
	if (ecss_verify_header_checksum(header) != 1)
	{
		return -1;  // Invalid checksum
	}

	return 0;  // Success
}

void ecss_create_header(ECSSPacketHeader* header, uint8_t service_type, uint16_t sequence_count,
                        uint16_t data_length, uint8_t is_telecommand)
{
	// Construct version/type/flags byte
	header->version_type_flags = (ECSS_VERSION << 5);
	header->version_type_flags |= (is_telecommand == 1 ? (1 << 4) : 0);

	header->service_type    = service_type;
	header->sequence_count  = sequence_count;
	header->data_length     = data_length;
	header->header_checksum = 0;  // Will be calculated during packing
}

void ecss_pack_header(const ECSSPacketHeader* header, uint8_t* buffer)
{
	// Pack the header fields into byte buffer
	buffer[0] = header->version_type_flags;
	buffer[1] = header->service_type;

	// Convert to big-endian for transmission
	uint16_t seq_be = HTONS(header->sequence_count);
	uint16_t len_be = HTONS(header->data_length);

	memcpy(&buffer[2], &seq_be, 2);
	memcpy(&buffer[4], &len_be, 2);

	// Calculate checksum on the actual byte buffer (first 6 bytes)
	uint8_t checksum = 0;
	for (int i = 0; i < 6; i++)
	{
		checksum ^= buffer[i];
	}
	buffer[6] = checksum;
}
