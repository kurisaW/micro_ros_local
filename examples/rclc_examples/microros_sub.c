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

#include <std_msgs/msg/string.h>  // Use string message type

#define DBG_TAG "sub_example"
#define DBG_LVL DBG_INFO
#include <rtdbg.h>

#define ARRAY_LEN 200

#define RCCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){printf("Failed status on line %d: %d. Aborting.\n",__LINE__,(int)temp_rc); return 1;}}
#define RCSOFTCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){printf("Failed status on line %d: %d. Continuing.\n",__LINE__,(int)temp_rc);}}

rcl_subscription_t subscriber;
std_msgs__msg__String msg;

char remote_addr[20] = {0};
char remote_port[10]= {0};

void subscription_callback(const void * msgin)
{
    const std_msgs__msg__String * msg = (const std_msgs__msg__String *)msgin;
    printf("I have heard: \"%s\"\n", msg->data.data);
}

static void microros_sub_string_thread_entry(void *parameter)
{

    rcl_allocator_t allocator = rcl_get_default_allocator();
    rclc_support_t support;

    // create init_options
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));

    // create node
    rcl_node_t node;
    RCCHECK(rclc_node_init_default(&node, "string_node", "", &support));

    // create subscriber
    RCCHECK(rclc_subscription_init_default(
        &subscriber,
        &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
        "/string_publisher"));

    // create executor
    rclc_executor_t executor = rclc_executor_get_zero_initialized_executor();
    RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
    RCCHECK(rclc_executor_add_subscription(&executor, &subscriber, &msg, &subscription_callback, ON_NEW_DATA));

    msg.data.data = (char * ) malloc(ARRAY_LEN * sizeof(char));
    msg.data.size = 0;
    msg.data.capacity = ARRAY_LEN;

    while(1)
    {
        rt_thread_mdelay(100);
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(100));
    }

    RCCHECK(rcl_subscription_fini(&subscriber, &node));
    RCCHECK(rcl_node_fini(&node));
}

static void set_transports(char *addr, char *port)
{
    rt_strncpy(remote_addr, addr, rt_strlen(addr));
    rt_strncpy(remote_port, port, rt_strlen(port));
    remote_addr[rt_strlen(addr)] = '\0';
    remote_port[rt_strlen(port)] = '\0';
}
static char *get_remote_addr()
{
    return remote_addr;
}

static int get_remote_port()
{
    return (uint32_t)atoi(remote_port);
}

static void microros_sub_string(int argc, char* argv[])
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
        set_microros_udp_transports(MICRO_ROS_UDP_IP, (uint32_t)atoi(MICRO_ROS_UDP_PORT));
        LOG_I("The current proxy IP address is [%s] | Agent port is [%s].", MICRO_ROS_UDP_IP, MICRO_ROS_UDP_PORT);
     }
     else
     {
        set_transports(argv[1], argv[2]);
        set_microros_udp_transports(get_remote_addr(), get_remote_port());
        LOG_I("The current proxy IP address is [%s] | Agent port is [%s].",remote_addr, remote_port);
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

    rt_thread_t thread = rt_thread_create("mr_substring", microros_sub_string_thread_entry, RT_NULL, 4096, 10, 10);
    if(thread != RT_NULL)
    {
        rt_thread_startup(thread);
        rt_kprintf("[micro_ros] New thread mr_substring\n");
    }
    else
    {
        rt_kprintf("[micro_ros] Failed to create thread mr_substring\n");
    }

    // Now you can publish a message to send a string
    // Example: ros2 topic pub --once /micro_ros_rtt_subscriber std_msgs/msg/String "{data: 'Hello, micro-ROS!'}"
}
MSH_CMD_EXPORT(microros_sub_string, micro ros subscribe string example)

#endif  // PKG_RCLC_EXAMPLE
