// Copyright 2019 Proyectos y Sistemas de Mantenimiento SL (eProsima).
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

#include <stdio.h> //printf
#include <string.h> //strcmp
#include <stdlib.h> //atoi

#define max_topics      5

#define STREAM_HISTORY  8
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    #define BUFFER_SIZE     UXR_CONFIG_SERIAL_TRANSPORT_MTU * STREAM_HISTORY
#elif defined(PKG_MICRO_ROS_USE_UDP)
    #define BUFFER_SIZE     UXR_CONFIG_UDP_TRANSPORT_MTU * STREAM_HISTORY
#else
    #define BUFFER_SIZE     UXR_CONFIG_TCP_TRANSPORT_MTU * STREAM_HISTORY
#endif

static void pub_helloworld_p2p_entry(void *arg)
{
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    uxrSerialTransport transport;
    
    if(!uxr_init_serial_transport(&transport, RT_NULL, 0, 1))
    {
        printf("Error at create transport.\n");
        return;
    }

#elif defined(PKG_MICRO_ROS_USE_TCP)
    uxrTCPTransport transport;

    if(!uxr_init_tcp_transport(&transport, UXR_IPv4, MICRO_ROS_TCP_IP, MICRO_ROS_TCP_PORT))
    {
        printf("Error at create transport.\n");
        return;
    }
#elif defined(PKG_MICRO_ROS_USE_UDP)
	uxrUDPTransport transport;

	if(!uxr_init_udp_transport(&transport, UXR_IPv4, MICRO_ROS_UDP_IP, MICRO_ROS_UDP_PORT))
    {
        printf("Error at create transport.\n");
        return;
    }
#endif

    // Session
    uxrSession session;
    uxr_init_session(&session, &transport.comm, 0xAAAABBBB);
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

    // Create entities
    uxrObjectId participant_id = uxr_object_id(0x01, UXR_PARTICIPANT_ID);
    const char* participant_ref = "participant_name";
    uint16_t participant_req = uxr_buffer_create_participant_ref(&session, reliable_out, participant_id, 0,
                    participant_ref, UXR_REPLACE);

    uxrObjectId topic_id = uxr_object_id(0x01, UXR_TOPIC_ID);
    const char* topic_ref = "topic_name";
    uint16_t topic_req = uxr_buffer_create_topic_ref(&session, reliable_out, topic_id, participant_id, topic_ref,
                    UXR_REPLACE);

    uxrObjectId publisher_id = uxr_object_id(0x01, UXR_PUBLISHER_ID);
    const char* publisher_xml = "";
    uint16_t publisher_req = uxr_buffer_create_publisher_xml(&session, reliable_out, publisher_id, participant_id,
                    publisher_xml, UXR_REPLACE);

    uxrObjectId datawriter_id = uxr_object_id(0x01, UXR_DATAWRITER_ID);
    const char* datawriter_ref = topic_ref;
    uint16_t datawriter_req = uxr_buffer_create_datawriter_xml(&session, reliable_out, datawriter_id, publisher_id,
                    datawriter_ref, UXR_REPLACE);

    // Send create entities message and wait its status
    uint8_t status[4];
    uint16_t requests[4] = {
        participant_req, topic_req, publisher_req, datawriter_req
    };
    if (!uxr_run_session_until_all_status(&session, 1000, requests, status, 4))
    {
        printf("Error at create entities: participant: %i topic: %i publisher: %i datawriter: %i\n", status[0],
                status[1], status[2], status[3]);
        return;
    }

    // Write topics
    bool connected = true;
    uint32_t count = 0;
    while (connected && count < max_topics)
    {
        HelloWorld topic = {
            ++count, "Hello DDS world!"
        };

        ucdrBuffer ub;
        uint32_t topic_size = HelloWorld_size_of_topic(&topic, 0);
        uxr_prepare_output_stream(&session, reliable_out, datawriter_id, &ub, topic_size);
        HelloWorld_serialize_topic(&ub, &topic);

        printf("Send topic: %s, id: %i\n", topic.message, topic.index);
        connected = uxr_run_session_time(&session, 1000);
    }

    // Delete resources
    uxr_delete_session(&session);
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    uxr_close_serial_transport(&transport);
#elif defined(PKG_MICRO_ROS_USE_TCP)
    uxr_close_tcp_transport(&transport);
#else
    uxr_close_udp_transport(&transport);
#endif

    printf("Exit demo.\n");
    return;
}

static void pub_helloworld_p2p(int argc, char** argv)
{
    rt_thread_t tid;

    tid = rt_thread_create("pub_p2p",
        pub_helloworld_p2p_entry, RT_NULL,
        10000, 25, 20);

    if(tid != RT_NULL)
    {
        rt_thread_startup(tid);
    }
    else
    {
        rt_kprintf("Failed to create pub_p2p thread!\n");
    }

    return;
}

MSH_CMD_EXPORT(pub_helloworld_p2p, micro-ros publish_helloworld_p2p demo.);

#endif  // PKG_UCLIENT_PLATFORM_EXAMPLE