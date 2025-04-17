#ifndef MICRO_ROS_RTT_H_
#define MICRO_ROS_RTT_H_

#include <rtthread.h>
#include <sys/time.h>

// ---- Build fixes -----
//Removing __attribute__ not supported by gcc-arm-none-eabi-5_4
// #define __attribute__(x)

#include <uxr/client/transport.h>
#include <rmw_microros/rmw_microros.h>

#if defined PKG_MICRO_ROS_USE_SERIAL

bool   micro_ros_serial_transport_open(struct uxrCustomTransport * transport);
bool   micro_ros_serial_transport_close(struct uxrCustomTransport * transport);
size_t micro_ros_serial_transport_write(struct uxrCustomTransport* transport, const uint8_t * buf, size_t len, uint8_t * err);
size_t micro_ros_serial_transport_read(struct uxrCustomTransport* transport, uint8_t* buf, size_t len, int timeout, uint8_t* err);
int clock_gettime(clockid_t unused, struct timespec *tp);

static inline void set_microros_transports(){
	rmw_uros_set_custom_transport(
		true,
		NULL,
		micro_ros_serial_transport_open,
		micro_ros_serial_transport_close,
		micro_ros_serial_transport_write,
		micro_ros_serial_transport_read
	);
}

#endif  // PKG_MICRO_ROS_USE_SERIAL

#if defined PKG_MICRO_ROS_USE_TCP

bool   micro_ros_tcp_transport_open(struct uxrCustomTransport * transport);
bool   micro_ros_tcp_transport_close(struct uxrCustomTransport * transport);
size_t micro_ros_tcp_transport_write(struct uxrCustomTransport* transport, const uint8_t * buf, size_t len, uint8_t * err);
size_t micro_ros_tcp_transport_read(struct uxrCustomTransport* transport, uint8_t* buf, size_t len, int timeout, uint8_t* err);
int clock_gettime(clockid_t unused, struct timespec *tp);

struct micro_ros_agent_locator {
    char* address;
    int port;
};

static inline void set_microros_tcp_transports(char * agent_ip, uint32_t agent_port){
    static struct micro_ros_agent_locator locator;
    locator.address = agent_ip;
    locator.port = agent_port;

    rmw_uros_set_custom_transport(
        false,
        (void *) &locator,
        micro_ros_tcp_transport_open,
        micro_ros_tcp_transport_close,
        micro_ros_tcp_transport_write,
        micro_ros_tcp_transport_read
    );
}

#endif  // PKG_MICRO_ROS_USE_TCP

#if defined PKG_MICRO_ROS_USE_UDP

bool   micro_ros_udp_transport_open(struct uxrCustomTransport * transport);
bool   micro_ros_udp_transport_close(struct uxrCustomTransport * transport);
size_t micro_ros_udp_transport_write(struct uxrCustomTransport* transport, const uint8_t * buf, size_t len, uint8_t * err);
size_t micro_ros_udp_transport_read(struct uxrCustomTransport* transport, uint8_t* buf, size_t len, int timeout, uint8_t* err);
int clock_gettime(clockid_t unused, struct timespec *tp);

struct micro_ros_agent_locator {
    char* address;
    int port;
};

static inline void set_microros_udp_transports(char * agent_ip, uint32_t agent_port){
    static struct micro_ros_agent_locator locator;
    locator.address = agent_ip;
    locator.port = agent_port;

    rmw_uros_set_custom_transport(
        false,
        (void *) &locator,
        micro_ros_udp_transport_open,
        micro_ros_udp_transport_close,
        micro_ros_udp_transport_write,
        micro_ros_udp_transport_read
    );
}

#endif  // PKG_MICRO_ROS_USE_UDP

#endif  // MICRO_ROS_RTT_H_