// Copyright 2017 Proyectos y Sistemas de Mantenimiento SL (eProsima).
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <rtthread.h>

#if defined(PKG_UCLIENT_PLATFORM_EXAMPLE)

#include "HelloWorld.h"

#include <uxr/client/client.h>
#include <ucdr/microcdr.h>

#include <stdio.h>
#include <string.h> //strcmp
#include <stdlib.h> //atoi

#define STREAM_HISTORY  8
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    #define BUFFER_SIZE     UXR_CONFIG_SERIAL_TRANSPORT_MTU * STREAM_HISTORY
#elif defined(PKG_MICRO_ROS_USE_UDP)
    #define BUFFER_SIZE     UXR_CONFIG_UDP_TRANSPORT_MTU * STREAM_HISTORY
#else
    #define BUFFER_SIZE     UXR_CONFIG_TCP_TRANSPORT_MTU * STREAM_HISTORY
#endif

static void xrcedds_pub_entry(int args, char **argv)
{   
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    uxrSerialTransport transport;
    
    if(!uxr_init_serial_transport(&transport, RT_NULL, 0, 1))
    {
        rt_kprintf("Error at create transport.\n");
        return;
    }

#elif defined(PKG_MICRO_ROS_USE_TCP)
    uxrTCPTransport transport;

    if(!uxr_init_tcp_transport(&transport, UXR_IPv4, MICRO_ROS_TCP_IP, MICRO_ROS_TCP_PORT))
    {
        rt_kprintf("Error at create transport.\n");
        return;
    }
#elif defined(PKG_MICRO_ROS_USE_UDP)
	uxrUDPTransport transport;

	if(!uxr_init_udp_transport(&transport, UXR_IPv4, MICRO_ROS_UDP_IP, MICRO_ROS_UDP_PORT))
    {
        rt_kprintf("Error at create transport.\n");
        return;
    }
#endif

    rt_kprintf("Micro-ROS micro xrce-dds publisher demo.\n");

    // Session
    uxrSession session;
    uxr_init_session(&session, &transport.comm, (uint32_t)atoi(argv[2]));
    if (!uxr_create_session(&session))
    {
        printf("Error at create session.\n");
        return;
    }

    // Streams
    uint8_t output_reliable_stream_buffer[BUFFER_SIZE];
    uxrStreamId reliable_out = uxr_create_output_reliable_stream(&session, output_reliable_stream_buffer, BUFFER_SIZE,
                    STREAM_HISTORY);

    uint8_t input_reliable_stream_buffer[BUFFER_SIZE];
    uxr_create_input_reliable_stream(&session, input_reliable_stream_buffer, BUFFER_SIZE, STREAM_HISTORY);

    uxrObjectId datawriter_id = uxr_object_id((uint16_t)atoi(argv[4]), UXR_DATAWRITER_ID);

    // Write topics
    bool connected = true;
    uint32_t count = 0;
    while (connected)
    {
        HelloWorld topic = {
            count++, "Hello DDS world!"
        };

        ucdrBuffer ub;
        uint32_t topic_size = HelloWorld_size_of_topic(&topic, 0);
        uxr_prepare_output_stream(&session, reliable_out, datawriter_id, &ub, topic_size);
        HelloWorld_serialize_topic(&ub, &topic);

        connected = uxr_run_session_time(&session, 1000);
        if (connected)
        {
            printf("Sent topic: %s, index: %i\n", topic.message, topic.index);
        }
    }

    // Delete resources
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    uxr_close_serial_transport(&transport);
#elif defined(PKG_MICRO_ROS_USE_TCP)
    uxr_close_tcp_transport(&transport);
#else
    uxr_close_udp_transport(&transport);
#endif

    rt_kprintf("Exit demo.\n");

    return;
}

static void xrcedds_pub(int args, char** argv)
{
    rt_thread_t tid;

    if (args < 5 || 0 != strcmp("--key", argv[1]) || 0 != strcmp("--id", argv[3])
            || 0 == atoi(argv[2]) || 0 == atoi(argv[4]))
    {
        rt_printf("usage: program [--key <number> --id <datawriter-number>]\n");
        return;
    }

    tid = rt_thread_create("xrcedds_pub",
        xrcedds_pub_entry, 
        RT_NULL,
        10240, RT_THREAD_PRIORITY_MAX/3, 20);

    if(tid != RT_NULL)
    {
        rt_thread_startup(tid);
    }
    else
    {
        rt_kprintf("Failed to create micro xrce-dds publisher thread!\n");
    }

    return;
}
MSH_CMD_EXPORT(xrcedds_pub, micro xrce-dds publisher demo.);

#endif  // PKG_UCLIENT_PLATFORM_EXAMPLE