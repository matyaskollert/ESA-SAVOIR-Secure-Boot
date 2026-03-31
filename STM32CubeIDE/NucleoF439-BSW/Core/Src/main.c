/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

#include <stdio.h>
#include "boot.h"
#include "input.h"
#include "update.h"
#include "report.h"
#include "self_test.h"
#include "flash.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define STANDBY_TIMEOUT_MS  15000
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
CRC_HandleTypeDef hcrc;

CRYP_HandleTypeDef hcryp;
__ALIGN_BEGIN static const uint32_t pKeyCRYP[6] __ALIGN_END = {
                            0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000};

HASH_HandleTypeDef hhash;

RNG_HandleTypeDef hrng;

UART_HandleTypeDef huart3;

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART3_UART_Init(void);
static void MX_CRYP_Init(void);
static void MX_HASH_Init(void);
static void MX_RNG_Init(void);
static void MX_CRC_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

int _write(int fd, char *ptr, int len)
{
    if (fd == 1 || fd == 2)
    {
        // Send debug output as ECSS DEBUG_LOG packet
        if (sendDebugPacket(&huart3, ptr, len) == 0)
            return len;
        else
            return -1;
    }
    return -1;
}

/* Map a received command byte to a BootloaderStatus */
static BootloaderStatus commandToStatus(uint8_t cmd)
{
	switch (cmd)
	{
		case '1': return BOOTLOADER_STATUS_NOMINAL;
		case '2': return BOOTLOADER_STATUS_UPDATE;
		case '3': return BOOTLOADER_STATUS_SWAP;
		case '4': return BOOTLOADER_STATUS_CHECK_VERSIONS;
		case '5': return BOOTLOADER_STATUS_RESET;
		case '6': return BOOTLOADER_STATUS_STANDBY;   /* no-op */
		default:  return BOOTLOADER_STATUS_UNKNOWN;
	}
}

static void handleRollback(UART_HandleTypeDef* uart); /* forward declaration */

/* Handle a swap command: verify preconditions, perform swap, reset */
static void handleSwap(UART_HandleTypeDef* uart, uint16_t sequence_count)
{
	if (checkSystemForImageSwap() != 0)
	{
		printf("Setting up system for image swap\r\n");
		sendNackPacket(uart, sequence_count, 12);
		setupSystemForImageSwap();
		NVIC_SystemReset();
	}
	if (checkUpdateVersion() != 0)
	{
		printf("Cannot update - rollback protection\r\n");
		sendNackPacket(uart, sequence_count, 9);
		setupSystemForNominal();
		NVIC_SystemReset();
	}
	if (sendAckPacket(uart, sequence_count) != 0)
	{
		printf("Error sending ACK for swap command\r\n");
	}
	if (swapBootWithUpdate() != 0)
	{
		printf("Swapping images failed\r\n");
		NVIC_SystemReset();
	}
	if (updateRollbackCounter() != 0)
	{
		printf("Updating rollback counter failed\r\n");
		NVIC_SystemReset();
	}
	setupSystemForNominal();
	NVIC_SystemReset();
}

/*
 * Standby command loop.
 * If initial_cmd is not BOOTLOADER_STATUS_STANDBY, it is dispatched immediately
 * using initial_seq as the sequence count; otherwise the loop waits for a command.
 */
static void standbyLoop(UART_HandleTypeDef* uart, BootloaderStatus initial_cmd, uint16_t initial_seq)
{
	BootloaderStatus cmd = initial_cmd;
	uint16_t seq = initial_seq;
	uint8_t use_initial = (initial_cmd != BOOTLOADER_STATUS_STANDBY);

	printf("Entering standby mode. Send: 1=boot, 2=update, 3=swap, 4=check versions, 5=reset\r\n");

	while (1)
	{
		if (!use_initial)
		{
			ECSSPacketHeader header;
			if (receivePacketHeader(uart, &header) != 0)
			{
				printf("Error receiving command header, retrying\r\n");
				continue;
			}
			uint8_t data = 0;
			if (header.data_length == 1)
			{
				if (receivePacketData(uart, &data, 1) != 0)
				{
					printf("Error receiving command data\r\n");
					continue;
				}
			}
			seq = header.sequence_count;
			cmd = commandToStatus(data);
		}
		use_initial = 0;

		switch (cmd)
		{
			case BOOTLOADER_STATUS_NOMINAL:
				/* Boot */
				if (checkSystemForNominal() != 0)
				{
					printf("ERROR: System not configured for nominal mode\r\n");
					sendNackPacket(uart, seq, 11);
					setupSystemForNominal();
					NVIC_SystemReset();
				}
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK\r\n");
				if (boot() != 0)
					printf("Booting image failed\r\n");
				break;

			case BOOTLOADER_STATUS_UPDATE:
				/* Update */
				if (checkSystemForUpdate() != 0)
				{
					printf("ERROR: System not configured for update\r\n");
					sendNackPacket(uart, seq, 10);
					setupSystemForUpdate();
					NVIC_SystemReset();
				}
				printf("System ready for update\r\n");
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK for command\r\n");
				if (receiveUpdateData(uart) != 0)
        {
					printf("Receiving image failed\r\n");
          break;
        }
				setupSystemForImageSwap();
				NVIC_SystemReset();
				break;

			case BOOTLOADER_STATUS_SWAP:
				/* Swap */
				handleSwap(uart, seq);
				break;

			case BOOTLOADER_STATUS_CHECK_VERSIONS:
				/* Check image versions */
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK for command\r\n");
				printImageHeaders();
				break;

			case BOOTLOADER_STATUS_RESET:
				/* Reset */
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK\r\n");
				NVIC_SystemReset();
				break;

			case BOOTLOADER_STATUS_ROLLBACK:
				/* Rollback */
				handleRollback(uart);
				break;

			case BOOTLOADER_STATUS_STANDBY:
				/* No-op (command '6') */
				if (sendAckPacket(uart, seq) != 0)
					printf("Error sending ACK\r\n");
				break;

			default:
				printf("Unknown command\r\n");
				sendNackPacket(uart, seq, 15);
				break;
		}
	}
}

/*
 * Check the rollback condition and act:
 *   - Rollback possible: configure for swap (sets status=123, re-arms OBs) and reset.
 *     The next boot will see status=123 and take the standard handleSwap path.
 *   - Rollback not possible: set status to STANDBY and enter the command loop.
 */
static void handleRollback(UART_HandleTypeDef* uart)
{
  printf("Boot failed - evaluating rollback\r\n");
  if (checkRollbackCondition() == 0)
  {
    printf("Initiating rollback swap\r\n");
    if (setupSystemForImageSwap() != 0)
    {
        printf("ERROR: Could not configure system for rollback, entering standby\r\n");
        setBootloaderStatus(BOOTLOADER_STATUS_STANDBY);
        standbyLoop(uart, BOOTLOADER_STATUS_STANDBY, 0);
        return;
    }
    /* OB change takes effect after reset; on next boot status=123 → handleSwap */
    NVIC_SystemReset();
  }
  else
  {
    printf("Rollback not applicable - entering standby\r\n");
    setBootloaderStatus(BOOTLOADER_STATUS_STANDBY);
    standbyLoop(uart, BOOTLOADER_STATUS_STANDBY, 0);
  }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART3_UART_Init();
  MX_CRYP_Init();
  MX_HASH_Init();
  MX_RNG_Init();
  MX_CRC_Init();
  /* USER CODE BEGIN 2 */

  // TODO: Add BSW CRC Check - where should the CRC be stored?

  printf("Performing self-tests\r\n");

  int16_t testResult = performSelfTests();
	if (testResult != 0)
	{
		printf("System is in an invalid state\r\n");
		NVIC_SystemReset();
	}

	BootloaderStatus status = getBootloaderStatus();
	printf("Waiting %d ms for manual input... (current status: 0x%02X)\r\n", STANDBY_TIMEOUT_MS, (unsigned int)status);

	ECSSPacketHeader cmd_header;
	int8_t inputReceived = receivePacketHeaderWithTimeout(&huart3, &cmd_header, STANDBY_TIMEOUT_MS);

	BootloaderStatus effective_cmd = BOOTLOADER_STATUS_STANDBY;
	uint16_t effective_seq = 0;

	if (inputReceived == 0)
	{
		/* Fully receive the packet and map the command byte to a BootloaderStatus */
		uint8_t data = 0;
		if (cmd_header.data_length == 1)
			receivePacketData(&huart3, &data, 1);

		if (data == '6')
		{
			/* Skip: ACK and defer to stored status */
			sendAckPacket(&huart3, cmd_header.sequence_count);
			printf("Skipping timeout, continuing with status: 0x%02X\r\n", (unsigned int)status);
			inputReceived = 1;
		}
		else
		{
			effective_cmd = commandToStatus(data);
			effective_seq = cmd_header.sequence_count;
		}
	}

	if (inputReceived != 0)
	{
		/* No user command (or skipped) - map stored status to effective command */
		effective_cmd = (status == BOOTLOADER_STATUS_BOOT_ATTEMPTED)
		                ? BOOTLOADER_STATUS_ROLLBACK
		                : status;
	}

	printf("Status: 0x%02X, Effective command: 0x%02X\r\n", (unsigned int)status, (unsigned int)effective_cmd);

	if (effective_cmd == BOOTLOADER_STATUS_NOMINAL)
	{
		/* ── NOMINAL ── */
		printf("Nominal mode - booting application\r\n");
		if (checkSystemForNominal() != 0)
		{
			printf("ERROR: System not configured for nominal mode\r\n");
      if (inputReceived == 0)
        sendNackPacket(&huart3, effective_seq, 11);
			setupSystemForNominal();
			NVIC_SystemReset();
		}
		if (sendAckPacket(&huart3, effective_seq) != 0)
			printf("Error sending ACK\r\n");
		if (boot() != 0)
		{
			printf("Booting image failed\r\n");
			handleRollback(&huart3);
		}
	}
	else
	{
		/* ── STANDBY ── */
		standbyLoop(&huart3, effective_cmd, effective_seq);
	}

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE3);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 192;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief CRC Initialization Function
  * @param None
  * @retval None
  */
static void MX_CRC_Init(void)
{

  /* USER CODE BEGIN CRC_Init 0 */

  /* USER CODE END CRC_Init 0 */

  /* USER CODE BEGIN CRC_Init 1 */

  /* USER CODE END CRC_Init 1 */
  hcrc.Instance = CRC;
  if (HAL_CRC_Init(&hcrc) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CRC_Init 2 */

  /* USER CODE END CRC_Init 2 */

}

/**
  * @brief CRYP Initialization Function
  * @param None
  * @retval None
  */
static void MX_CRYP_Init(void)
{

  /* USER CODE BEGIN CRYP_Init 0 */

  /* USER CODE END CRYP_Init 0 */

  /* USER CODE BEGIN CRYP_Init 1 */

  /* USER CODE END CRYP_Init 1 */
  hcryp.Instance = CRYP;
  hcryp.Init.DataType = CRYP_DATATYPE_32B;
  hcryp.Init.pKey = (uint32_t *)pKeyCRYP;
  hcryp.Init.Algorithm = CRYP_TDES_ECB;
  hcryp.Init.DataWidthUnit = CRYP_DATAWIDTHUNIT_WORD;
  if (HAL_CRYP_Init(&hcryp) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CRYP_Init 2 */

  /* USER CODE END CRYP_Init 2 */

}

/**
  * @brief HASH Initialization Function
  * @param None
  * @retval None
  */
static void MX_HASH_Init(void)
{

  /* USER CODE BEGIN HASH_Init 0 */

  /* USER CODE END HASH_Init 0 */

  /* USER CODE BEGIN HASH_Init 1 */

  /* USER CODE END HASH_Init 1 */
  hhash.Init.DataType = HASH_DATATYPE_32B;
  if (HAL_HASH_Init(&hhash) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN HASH_Init 2 */

  /* USER CODE END HASH_Init 2 */

}

/**
  * @brief RNG Initialization Function
  * @param None
  * @retval None
  */
static void MX_RNG_Init(void)
{

  /* USER CODE BEGIN RNG_Init 0 */

  /* USER CODE END RNG_Init 0 */

  /* USER CODE BEGIN RNG_Init 1 */

  /* USER CODE END RNG_Init 1 */
  hrng.Instance = RNG;
  if (HAL_RNG_Init(&hrng) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN RNG_Init 2 */

  /* USER CODE END RNG_Init 2 */

}

/**
  * @brief USART3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART3_UART_Init(void)
{

  /* USER CODE BEGIN USART3_Init 0 */

  /* USER CODE END USART3_Init 0 */

  /* USER CODE BEGIN USART3_Init 1 */

  /* USER CODE END USART3_Init 1 */
  huart3.Instance = USART3;
  huart3.Init.BaudRate = 115200;
  huart3.Init.WordLength = UART_WORDLENGTH_8B;
  huart3.Init.StopBits = UART_STOPBITS_1;
  huart3.Init.Parity = UART_PARITY_NONE;
  huart3.Init.Mode = UART_MODE_TX_RX;
  huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart3.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart3) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART3_Init 2 */

  /* USER CODE END USART3_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
