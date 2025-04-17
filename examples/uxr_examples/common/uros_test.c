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
#include <stdlib.h>

#if defined(PKG_UCLIENT_PLATFORM_EXAMPLE)

#include <uxr/client/client.h>
#include <ucdr/microcdr.h>

#include "XRCE_DDS_Header.h"

#define STREAM_HISTORY  5
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    #define BUFFER_SIZE     UXR_CONFIG_SERIAL_TRANSPORT_MTU * STREAM_HISTORY
#elif defined(PKG_MICRO_ROS_USE_UDP)
    #define BUFFER_SIZE     UXR_CONFIG_UDP_TRANSPORT_MTU * STREAM_HISTORY
#else
    #define BUFFER_SIZE     UXR_CONFIG_TCP_TRANSPORT_MTU * STREAM_HISTORY
#endif

static int recv_ping = 0;

void msgs_on_topic(
        uxrSession* session,
        uxrObjectId object_id,
        uint16_t request_id,
        uxrStreamId stream_id,
        struct ucdrBuffer* ub,
        uint16_t length,
        void* args)
{
    (void) session; (void) object_id; (void) request_id; (void) stream_id; (void) length;

    Header topic;
    Header_deserialize_topic(ub, &topic);

    rt_kprintf("Received topic: %s, sec: %ld\n", topic.frame_id, topic.stamp.sec);

    recv_ping = 1;
}

static void uros_entry(void *arg)
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

    rt_kprintf("Micro-ROS ping-pong demo.\n");

    // Session
    uxrSession session;
    uxr_init_session(&session, &transport.comm, 0xABCDABCD);
    uxr_set_topic_callback(&session, msgs_on_topic, NULL);
    if(!uxr_create_session(&session))
    {
        rt_kprintf("Error at create session.\n");
        return;
    }

    // Streams
    uint8_t output_reliable_stream_buffer[BUFFER_SIZE];
    uxrStreamId reliable_out = uxr_create_output_reliable_stream(&session, output_reliable_stream_buffer, BUFFER_SIZE, STREAM_HISTORY);

    uint8_t input_reliable_stream_buffer[BUFFER_SIZE];
    uxrStreamId reliable_in = uxr_create_input_reliable_stream(&session, input_reliable_stream_buffer, BUFFER_SIZE, STREAM_HISTORY);

    // Create entities
    uxrObjectId participant_id = uxr_object_id(0x01, UXR_PARTICIPANT_ID);
    const char* participant_xml = "<dds>"
                                      "<participant>"
                                          "<rtps>"
                                              "<name>pingpong_node</name>"
                                          "</rtps>"
                                      "</participant>"
                                  "</dds>";
    uint16_t participant_req = uxr_buffer_create_participant_xml(&session, reliable_out, participant_id, 0, participant_xml, UXR_REPLACE);

    uxrObjectId topic_ping_id = uxr_object_id(0x01, UXR_TOPIC_ID);
    const char* topic_ping_xml = "<dds>"
                                "<topic>"
                                    "<name>rt/microROS/ping</name>"
                                    "<dataType>std_msgs::msg::dds_::Header_</dataType>"
                                "</topic>"
                            "</dds>";
    uint16_t topic_ping_req = uxr_buffer_create_topic_xml(&session, reliable_out, topic_ping_id, participant_id, topic_ping_xml, UXR_REPLACE);

    uxrObjectId topic_pong_id = uxr_object_id(0x02, UXR_TOPIC_ID);
    const char* topic_pong_xml = "<dds>"
                                "<topic>"
                                    "<name>rt/microROS/pong</name>"
                                    "<dataType>std_msgs::msg::dds_::Header_</dataType>"
                                "</topic>"
                            "</dds>";
    uint16_t topic_pong_req = uxr_buffer_create_topic_xml(&session, reliable_out, topic_pong_id, participant_id, topic_pong_xml, UXR_REPLACE);

    uxrObjectId publisher_id = uxr_object_id(0x01, UXR_PUBLISHER_ID);
    const char* publisher_xml = "";
    uint16_t publisher_req = uxr_buffer_create_publisher_xml(&session, reliable_out, publisher_id, participant_id, publisher_xml, UXR_REPLACE);

    uxrObjectId subscriber_id = uxr_object_id(0x01, UXR_SUBSCRIBER_ID);
    const char* subscriber_xml = "";
    uint16_t subscriber_req = uxr_buffer_create_subscriber_xml(&session, reliable_out, subscriber_id, participant_id, subscriber_xml, UXR_REPLACE);

    uxrObjectId datawriter_id = uxr_object_id(0x01, UXR_DATAWRITER_ID);
    const char* datawriter_xml = "<dds>"
                                    "<data_writer>"
                                        "<topic>"
                                            "<kind>NO_KEY</kind>"
                                            "<name>rt/microROS/pong</name>"
                                            "<dataType>std_msgs::msg::dds_::Header_</dataType>"
                                        "</topic>"
                                    "</data_writer>"
                                 "</dds>";
    uint16_t datawriter_req = uxr_buffer_create_datawriter_xml(&session, reliable_out, datawriter_id, publisher_id, datawriter_xml, UXR_REPLACE);

    uxrObjectId datareader_id = uxr_object_id(0x01, UXR_DATAREADER_ID);
    const char* datareader_xml = "<dds>"
                                    "<data_reader>"
                                        "<topic>"
                                            "<kind>NO_KEY</kind>"
                                            "<name>rt/microROS/ping</name>"
                                            "<dataType>std_msgs::msg::dds_::Header_</dataType>"
                                        "</topic>"
                                    "</data_reader>"
                                 "</dds>";
    uint16_t datareader_req = uxr_buffer_create_datareader_xml(&session, reliable_out, datareader_id, subscriber_id, datareader_xml, UXR_REPLACE);

    uint8_t status[7]; // we have 7 request to check.
    uint16_t requests[7] = {participant_req, topic_ping_req, topic_pong_req, publisher_req, subscriber_req, datawriter_req, datareader_req};
    if(!uxr_run_session_until_all_status(&session, 1000, requests, status, 7))
    {
        rt_kprintf("Error at create entities: participant: %i topic: %i %i publisher: %i darawriter: %i subscriber: %i datareader: %i\n", 
                    status[0], status[1], status[2], status[3], status[4], status[5], status[6]);
        return;
    }

    // Write topics
    bool connected = true;
    uint32_t count = 0;
    Header topic;
    rt_sprintf(topic.frame_id, "Hello RT-Thread!");

    // Request topics
    uxrDeliveryControl delivery_control = {0};
    delivery_control.max_samples = UXR_MAX_SAMPLES_UNLIMITED;
    uxr_buffer_request_data(&session, reliable_out, datareader_id, reliable_in, &delivery_control);

    rt_kprintf("Wait for ping topic\n");
    while(connected && count < 100)
    {
        if(recv_ping) {
            uint32_t time_now_ms = rt_tick_get_millisecond();
            topic.stamp.sec = time_now_ms / 1000;
            topic.stamp.nanosec = (time_now_ms % 1000) * 1e6;

            ucdrBuffer ub;
            uint32_t topic_size = Header_size_of_topic(&topic, 0);
            uxr_prepare_output_stream(&session, reliable_out, datawriter_id, &ub, topic_size);
            Header_serialize_topic(&ub, &topic);

            rt_kprintf("Send pong topic: %s, sec: %ld\n", topic.frame_id, topic.stamp.sec);

            recv_ping = 0;
            count++;
        }

        connected = uxr_run_session_until_data(&session, 1000 * 300);
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

    rt_kprintf("Exit demo.\n");

    return;
}

static void uros_test(int argc, char** argv)
{
    rt_thread_t tid;

    tid = rt_thread_create("uros_client",
        uros_entry, RT_NULL,
        10240, RT_THREAD_PRIORITY_MAX/3, 20);

    if(tid != RT_NULL)
    {
        rt_thread_startup(tid);
    }
    else
    {
        rt_kprintf("Failed to create uros_client thread!\n");
    }

    return;
}

MSH_CMD_EXPORT(uros_test, micro-ros ping-pong demo.);

#endif  // PKG_UCLIENT_PLATFORM_EXAMPLE