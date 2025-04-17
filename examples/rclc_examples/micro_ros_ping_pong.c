/*
 * Copyright (c) 2006-2023, RT-Thread Development Team
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Change Logs:
 * Date           Author       Notes
 * 2023-12-06     Wangyuqiang  the first version
 */

#include <rtthread.h>

#if defined(PKG_RCLC_EXAMPLE)

#include "micro_ros_rtt.h"

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <std_msgs/msg/header.h>

#include <stdio.h>
#include <unistd.h>
#include <time.h>

#define DBG_TAG "ping_pong"
#define DBG_LVL DBG_INFO
#include <rtdbg.h>

#define STRING_BUFFER_LEN 100

#define RCCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){printf("Failed status on line %d: %d. Aborting.\n",__LINE__,(int)temp_rc); return;}}
#define RCSOFTCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){printf("Failed status on line %d: %d. Continuing.\n",__LINE__,(int)temp_rc);}}

static rcl_publisher_t ping_publisher;
static rcl_publisher_t pong_publisher;
static rcl_subscription_t ping_subscriber;
static rcl_subscription_t pong_subscriber;

static std_msgs__msg__Header incoming_ping;
static std_msgs__msg__Header outcoming_ping;
static std_msgs__msg__Header incoming_pong;

static rclc_executor_t executor;
static rcl_node_t node;

static int device_id;
static int seq_no;
static int pong_count;

void ping_timer_callback(rcl_timer_t * timer, int64_t last_call_time)
{
	(void) last_call_time;

	if (timer != NULL) {

		seq_no = rand();
		rt_sprintf(outcoming_ping.frame_id.data, "%d_%d", seq_no, device_id);
		outcoming_ping.frame_id.size = strlen(outcoming_ping.frame_id.data);

		// Fill the message timestamp
		struct timespec ts;
		clock_gettime(CLOCK_REALTIME, &ts);
		outcoming_ping.stamp.sec = ts.tv_sec;
		outcoming_ping.stamp.nanosec = ts.tv_nsec;

		// Reset the pong count and publish the ping message
		pong_count = 0;
		RCSOFTCHECK(rcl_publish(&ping_publisher, (const void*)&outcoming_ping, NULL));
		rt_kprintf("Ping send seq %s\n", outcoming_ping.frame_id.data);
	}
}

void ping_subscription_callback(const void * msgin)
{
	const std_msgs__msg__Header * msg = (const std_msgs__msg__Header *)msgin;

	rt_kprintf("ping_subscription_callback\n");

	// Dont pong my own pings
	if(strcmp(outcoming_ping.frame_id.data, msg->frame_id.data) != 0){
		rt_kprintf("Ping received with seq %s. Answering.\n", msg->frame_id.data);
		RCSOFTCHECK(rcl_publish(&ping_publisher, (const void*)msg, NULL));
	}
}


void pong_subscription_callback(const void * msgin)
{
	const std_msgs__msg__Header * msg = (const std_msgs__msg__Header *)msgin;

	rt_kprintf("pong_subscription_callback\n");

	if(strcmp(outcoming_ping.frame_id.data, msg->frame_id.data) == 0) {
			pong_count++;
			rt_kprintf("Pong for seq %s (%d)\n", msg->frame_id.data, pong_count);
	}
}

static void microros_ping_pong_thread_entry(void *parameter)
{
    rcl_allocator_t allocator;
    rclc_support_t support;
    rcl_timer_t timer;

	allocator = rcl_get_default_allocator();

	// create init_options
	RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));

	// create node
	RCCHECK(rclc_node_init_default(&node, "pingpong_node", "", &support));

	// Create a reliable ping publisher
	RCCHECK(rclc_publisher_init_default(&ping_publisher, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Header), "/microROS/ping"));

	// Create a best effort pong publisher
	RCCHECK(rclc_publisher_init_best_effort(&pong_publisher, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Header), "/microROS/pong"));

	// Create a best effort ping subscriber
	RCCHECK(rclc_subscription_init_best_effort(&ping_subscriber, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Header), "/microROS/ping"));

	// Create a best effort  pong subscriber
	RCCHECK(rclc_subscription_init_best_effort(&pong_subscriber, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Header), "/microROS/pong"));

	// Create a 3 seconds ping timer timer,
	RCCHECK(rclc_timer_init_default(&timer, &support, RCL_MS_TO_NS(2000), ping_timer_callback));

	// Create executor
	executor = rclc_executor_get_zero_initialized_executor();

	RCCHECK(rclc_executor_init(&executor, &support.context, 3, &allocator));
	RCCHECK(rclc_executor_add_timer(&executor, &timer));
	RCCHECK(rclc_executor_add_subscription(&executor, &ping_subscriber, &incoming_ping, &ping_subscription_callback, ON_NEW_DATA));
	RCCHECK(rclc_executor_add_subscription(&executor, &pong_subscriber, &incoming_pong, &pong_subscription_callback, ON_NEW_DATA));

	// Create and allocate the pingpong messages

	char outcoming_ping_buffer[STRING_BUFFER_LEN];
	outcoming_ping.frame_id.data = outcoming_ping_buffer;
	outcoming_ping.frame_id.capacity = STRING_BUFFER_LEN;

	char incoming_ping_buffer[STRING_BUFFER_LEN];
	incoming_ping.frame_id.data = incoming_ping_buffer;
	incoming_ping.frame_id.capacity = STRING_BUFFER_LEN;

	char incoming_pong_buffer[STRING_BUFFER_LEN];
	incoming_pong.frame_id.data = incoming_pong_buffer;
	incoming_pong.frame_id.capacity = STRING_BUFFER_LEN;

    device_id = rand();

	rt_kprintf("[micro_ros] micro_ros init successful.\n");

	while(1)
	{
		rt_thread_mdelay(100);
		rclc_executor_spin_some(&executor, RCL_MS_TO_NS(100));
	}

	RCCHECK(rcl_publisher_fini(&ping_publisher, &node));
    RCCHECK(rcl_publisher_fini(&pong_publisher, &node));
    RCCHECK(rcl_subscription_fini(&ping_subscriber, &node));
    RCCHECK(rcl_subscription_fini(&pong_subscriber, &node));
    RCCHECK(rcl_node_fini(&node));
}

static void microros_ping_pong(int argc,char* argv[])
{
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    // Serial setup
     set_microros_transports();

#elif defined(PKG_MICRO_ROS_USE_UDP)
    // UDP setup
     if(argc == 1)
     {
		if((MICRO_ROS_UDP_IP == RT_NULL) && (MICRO_ROS_UDP_PORT == RT_NULL))
		{
			LOG_E("Please refer to the parameters correctly!");
			LOG_E("Or you should define the 'MICRO_ROS_UDP_IP' and 'MICRO_ROS_UDP_PORT' variables in the rtconfig.h file");
		}
        set_microros_udp_transports(MICRO_ROS_UDP_IP, MICRO_ROS_UDP_PORT);
        LOG_I("The current proxy IP address is [%s] | Agent port is [%s].", MICRO_ROS_UDP_IP, MICRO_ROS_UDP_PORT);
     }
     else
     {
        set_microros_udp_transports(argv[1], (atoi)(argv[2]));
        LOG_I("The current proxy IP address is [%s] | Agent port is [%s].",argv[1], argv[2]);
     }

#elif defined(PKG_MICRO_ROS_USE_TCP)
    // TCP setup
     if(argc == 1) 
     {
		if((MICRO_ROS_TCP_IP == RT_NULL) && (MICRO_ROS_TCP_PORT == RT_NULL))
		{
			LOG_E("Please refer to the parameters correctly!");
			OG_E("Or you should define the 'MICRO_ROS_TCP_IP' and 'MICRO_ROS_TCP_PORT' variables in the rtconfig.h file");
		}
        set_microros_tcp_transports(MICRO_ROS_TCP_IP, MICRO_ROS_TCP_PORT);
        LOG_I("The current proxy IP address is [%s] | Agent port is [%s].", MICRO_ROS_TCP_IP, MICRO_ROS_TCP_PORT);
     }
     else
     {
        set_microros_tcp_transports(argv[1], (atoi)(argv[2]));
        LOG_I("The current proxy IP address is [%s] | Agent port is [%s].",argv[1], argv[2]);
     }
#endif

	rt_thread_t thread = rt_thread_create("pi_po", microros_ping_pong_thread_entry, RT_NULL, 8196,25,10);
	if(thread != RT_NULL)
	{
		rt_thread_startup(thread);
		rt_kprintf("[micro_ros] New thread ping_pong\n");
	}
	else
	{
		rt_kprintf("[micro_ros] Failed to create thread ping_pong\n");
	}
}
MSH_CMD_EXPORT(microros_ping_pong, micro ros ping_pong example);

#endif	// PKG_RCLC_EXAMPLE
