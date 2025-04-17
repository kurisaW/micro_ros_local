// Copyright 2017-present Proyectos y Sistemas de Mantenimiento SL (eProsima).
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

#include <uxr/client/client.h>

#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#ifdef WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif /* ifdef WIN32 */

static int64_t avg_time_offset = 0;
static size_t sample_id = 0;

static void on_time(
        uxrSession* session,
        int64_t current_time,
        int64_t transmit_timestamp,
        int64_t received_timestamp,
        int64_t originate_timestamp,
        void* args)
{
    (void) args;
    int64_t current_time_offset = ((current_time - originate_timestamp) - (transmit_timestamp - received_timestamp)) /
            2;
    avg_time_offset = (avg_time_offset * sample_id + current_time_offset) / (sample_id + 1);
    ++sample_id;
    session->time_offset = avg_time_offset;
}

static void time_sync_cb_entry(void *arg)
{
#if defined(PKG_MICRO_ROS_USE_SERIAL)
    printf("This demo does not support serial mode. Please select UDP or TCP transmission mode.\n");
    return;

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
    uxr_init_session(&session, &transport.comm, 0xCCCCDDDD);
    if (!uxr_create_session(&session))
    {
        printf("Error at create session.\n");
        return;
    }

    // Set time-callback.
    uxr_set_time_callback(&session, on_time, NULL);

    // Synchronize with the Agent
    bool synchronized = false;
    do
    {
        synchronized = uxr_sync_session(&session, 1000);
        
        printf("synchronized with time offset %-5" PRId64 "us\n", session.time_offset / 1000);
        rt_thread_mdelay(1000);

    } while (synchronized);

    // Delete resources
    uxr_delete_session(&session);
#if defined(PKG_MICRO_ROS_USE_TCP)
    uxr_close_tcp_transport(&transport);
#elif defined(PKG_MICRO_ROS_USE_UDP)
    uxr_close_udp_transport(&transport);
#endif

    return;
}

static void time_sync_cb(int argc, char** argv)
{
    rt_thread_t tid;

    tid = rt_thread_create("tim_sync_cb",
                            time_sync_cb_entry,
                            RT_NULL,
                            8192,
                            25,
                            20);

    if(tid != RT_NULL)
    {
        rt_thread_startup(tid);
    }
    else
    {
        rt_kprintf("Failed to create tim_sync_cb thread!\n");
    }

    return;
}
MSH_CMD_EXPORT(time_sync_cb, micro-ros time sync callback demo.);

#endif // PKG_UCLIENT_PLATFORM_EXAMPLE