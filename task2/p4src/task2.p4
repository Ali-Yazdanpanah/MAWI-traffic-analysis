#include <core.p4>
#include <v1model.p4>

typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;
typedef bit<128> ip6Addr_t;

const bit<32> NUM_FLOWS = 16384;
const bit<32> IPV6_HDR_LEN = 40;

// UDP INT report export (collector = h2 in topo/topology.json).
const bit<16> INT_COLLECTOR_PORT = 4790;
const ip4Addr_t COLLECTOR_IPV4 = 32w0x0A000002;       // 10.0.0.2
const ip4Addr_t SWITCH_REPORT_IPV4 = 32w0x0A0000FE;   // 10.0.0.254
const macAddr_t COLLECTOR_MAC = 48w0x000000000002;
const macAddr_t REPORT_SRC_MAC = 48w0x0000000000FE;
const bit<32> INT_REPORT_MAGIC = 32w0x494E5431;         // "INT1"
const bit<16> INT_REPORT_PAYLOAD_LEN = 50;
const bit<16> INT_UDP_PKT_LEN = 78;                     // IPv4(20) + UDP(8) + payload
const bit<32> CLONE_SESSION_INT = 1;
const bit<32> PKT_INSTANCE_TYPE_EGRESS_CLONE = 2;

// BMv2 ingress_global_timestamp is in microseconds.
const bit<48> TS_NEVER = 0;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

header ipv6_t {
    bit<4>       version;
    bit<8>       trafficClass;
    bit<20>      flowLabel;
    bit<16>      payloadLength;
    bit<8>       nextHeader;
    bit<8>       hopLimit;
    ip6Addr_t    srcAddr;
    ip6Addr_t    dstAddr;
}

header tcp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<4>  reserved;
    bit<8>  flags;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

header udp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<16> length_;
    bit<16> checksum;
}

header icmp_t {
    bit<8>  type_;
    bit<8>  code;
    bit<16> checksum;
}

// Task II telemetry shim (appended on egress port 2 only; see MyEgress).
header telemetry_t {
    bit<8>  flags;              // bit0: iat_valid
    bit<8>  reserved;
    bit<48> iat_us;             // global IAT in microseconds
    bit<32> flow_id;
    bit<32> flow_pkt_count;     // packet count before this packet
    bit<32> flow_byte_count;    // byte sum before this packet (L3 length)
    bit<48> flow_first_ts_us;
    bit<48> flow_last_ts_us;    // updated to current packet timestamp
}

// Serialized into UDP payload for INT export mode (see MyEgress.build_udp_int_report).
header int_report_t {
    bit<32> magic;
    bit<8>  flags;
    bit<8>  reserved;
    bit<48> iat_us;
    bit<32> flow_id;
    bit<32> flow_pkt_count;
    bit<32> flow_byte_count;
    bit<48> flow_first_ts_us;
    bit<48> flow_last_ts_us;
    bit<32> ipv4_src;
    bit<32> ipv4_dst;
    bit<8>  ip_proto;
    bit<8>  ip_version;
    bit<16> src_port;
    bit<16> dst_port;
    bit<32> l3_byte_len;
}

struct metadata {
    bit<32> flow_id;
    bit<32> current_pkt_count;
    bit<32> current_byte_count;
    bit<48> packet_iat_us;
    bit<32> l3_byte_len;
    bit<2>  export_mode; // 0=in-band, 1=UDP INT, 2=both
}

struct headers {
    ethernet_t  ethernet;
    ipv4_t      ipv4;
    ipv6_t      ipv6;
    tcp_t       tcp;
    udp_t       udp;
    icmp_t      icmp;
    telemetry_t telemetry;
    int_report_t int_report;
}

parser MyParser(packet_in packet, out headers hdr, inout metadata meta, inout standard_metadata_t standard_metadata) {
    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            16w0x0800: parse_ipv4;
            16w0x86DD: parse_ipv6;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            8w6: parse_tcp;
            8w17: parse_udp;
            8w1: parse_icmp;
            default: accept;
        }
    }

    state parse_ipv6 {
        packet.extract(hdr.ipv6);
        transition select(hdr.ipv6.nextHeader) {
            8w6: parse_tcp;
            8w17: parse_udp;
            8w58: parse_icmp;
            default: accept;
        }
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }

    state parse_udp {
        packet.extract(hdr.udp);
        transition accept;
    }

    state parse_icmp {
        packet.extract(hdr.icmp);
        transition accept;
    }
}

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

control MyIngress(inout headers hdr, inout metadata meta, inout standard_metadata_t standard_metadata) {
    register<bit<32>>(NUM_FLOWS) flow_packet_count;
    register<bit<32>>(NUM_FLOWS) flow_byte_count;
    register<bit<48>>(NUM_FLOWS) flow_first_ts;
    register<bit<48>>(NUM_FLOWS) flow_last_ts;

    register<bit<48>>(1) last_packet_timestamp;
    register<bit<1>>(1) last_ts_valid;

    action set_export_inband() {
        meta.export_mode = 2w0;
    }

    action set_export_udp() {
        meta.export_mode = 2w1;
    }

    action set_export_both() {
        meta.export_mode = 2w2;
    }

    action noop_export_mode() { }

    table configure_export_mode {
        key = {
            standard_metadata.ingress_port : exact;
        }
        actions = {
            set_export_inband;
            set_export_udp;
            set_export_both;
            noop_export_mode;
        }
        default_action = noop_export_mode();
        size = 4;
    }

    action canonical_flow_hash_v4(ip4Addr_t a, ip4Addr_t b, bit<8> proto, bit<16> p1, bit<16> p2) {
        hash(meta.flow_id, HashAlgorithm.crc16, (bit<32>)0,
             {a, b, proto, p1, p2}, NUM_FLOWS);
    }

    action canonical_flow_hash_v6(ip6Addr_t a, ip6Addr_t b, bit<8> proto, bit<16> p1, bit<16> p2) {
        hash(meta.flow_id, HashAlgorithm.crc16, (bit<32>)0,
             {a, b, proto, p1, p2}, NUM_FLOWS);
    }

    action hash_ipv4_flow() {
        bit<16> icmp_type = (bit<16>)hdr.icmp.type_;
        bit<16> icmp_code = (bit<16>)hdr.icmp.code;

        if (hdr.tcp.isValid()) {
            if (hdr.ipv4.srcAddr < hdr.ipv4.dstAddr
                || (hdr.ipv4.srcAddr == hdr.ipv4.dstAddr && hdr.tcp.srcPort <= hdr.tcp.dstPort)) {
                canonical_flow_hash_v4(
                    hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol,
                    hdr.tcp.srcPort, hdr.tcp.dstPort);
            } else {
                canonical_flow_hash_v4(
                    hdr.ipv4.dstAddr, hdr.ipv4.srcAddr, hdr.ipv4.protocol,
                    hdr.tcp.dstPort, hdr.tcp.srcPort);
            }
        } else if (hdr.udp.isValid()) {
            if (hdr.ipv4.srcAddr < hdr.ipv4.dstAddr
                || (hdr.ipv4.srcAddr == hdr.ipv4.dstAddr && hdr.udp.srcPort <= hdr.udp.dstPort)) {
                canonical_flow_hash_v4(
                    hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol,
                    hdr.udp.srcPort, hdr.udp.dstPort);
            } else {
                canonical_flow_hash_v4(
                    hdr.ipv4.dstAddr, hdr.ipv4.srcAddr, hdr.ipv4.protocol,
                    hdr.udp.dstPort, hdr.udp.srcPort);
            }
        } else if (hdr.icmp.isValid()) {
            if (hdr.ipv4.srcAddr <= hdr.ipv4.dstAddr) {
                canonical_flow_hash_v4(
                    hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol,
                    icmp_type, icmp_code);
            } else {
                canonical_flow_hash_v4(
                    hdr.ipv4.dstAddr, hdr.ipv4.srcAddr, hdr.ipv4.protocol,
                    icmp_type, icmp_code);
            }
        } else {
            if (hdr.ipv4.srcAddr <= hdr.ipv4.dstAddr) {
                canonical_flow_hash_v4(
                    hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol,
                    16w0, 16w0);
            } else {
                canonical_flow_hash_v4(
                    hdr.ipv4.dstAddr, hdr.ipv4.srcAddr, hdr.ipv4.protocol,
                    16w0, 16w0);
            }
        }
    }

    action hash_ipv6_flow() {
        bit<16> icmp_type = (bit<16>)hdr.icmp.type_;
        bit<16> icmp_code = (bit<16>)hdr.icmp.code;

        if (hdr.tcp.isValid()) {
            if (hdr.ipv6.srcAddr < hdr.ipv6.dstAddr
                || (hdr.ipv6.srcAddr == hdr.ipv6.dstAddr && hdr.tcp.srcPort <= hdr.tcp.dstPort)) {
                canonical_flow_hash_v6(
                    hdr.ipv6.srcAddr, hdr.ipv6.dstAddr, hdr.ipv6.nextHeader,
                    hdr.tcp.srcPort, hdr.tcp.dstPort);
            } else {
                canonical_flow_hash_v6(
                    hdr.ipv6.dstAddr, hdr.ipv6.srcAddr, hdr.ipv6.nextHeader,
                    hdr.tcp.dstPort, hdr.tcp.srcPort);
            }
        } else if (hdr.udp.isValid()) {
            if (hdr.ipv6.srcAddr < hdr.ipv6.dstAddr
                || (hdr.ipv6.srcAddr == hdr.ipv6.dstAddr && hdr.udp.srcPort <= hdr.udp.dstPort)) {
                canonical_flow_hash_v6(
                    hdr.ipv6.srcAddr, hdr.ipv6.dstAddr, hdr.ipv6.nextHeader,
                    hdr.udp.srcPort, hdr.udp.dstPort);
            } else {
                canonical_flow_hash_v6(
                    hdr.ipv6.dstAddr, hdr.ipv6.srcAddr, hdr.ipv6.nextHeader,
                    hdr.udp.dstPort, hdr.udp.srcPort);
            }
        } else if (hdr.icmp.isValid()) {
            if (hdr.ipv6.srcAddr <= hdr.ipv6.dstAddr) {
                canonical_flow_hash_v6(
                    hdr.ipv6.srcAddr, hdr.ipv6.dstAddr, hdr.ipv6.nextHeader,
                    icmp_type, icmp_code);
            } else {
                canonical_flow_hash_v6(
                    hdr.ipv6.dstAddr, hdr.ipv6.srcAddr, hdr.ipv6.nextHeader,
                    icmp_type, icmp_code);
            }
        } else {
            if (hdr.ipv6.srcAddr <= hdr.ipv6.dstAddr) {
                canonical_flow_hash_v6(
                    hdr.ipv6.srcAddr, hdr.ipv6.dstAddr, hdr.ipv6.nextHeader,
                    16w0, 16w0);
            } else {
                canonical_flow_hash_v6(
                    hdr.ipv6.dstAddr, hdr.ipv6.srcAddr, hdr.ipv6.nextHeader,
                    16w0, 16w0);
            }
        }
    }

    apply {
        meta.l3_byte_len = 0;
        meta.export_mode = 2w0;

        if (hdr.ipv4.isValid()) {
            meta.l3_byte_len = (bit<32>)hdr.ipv4.totalLen;
            configure_export_mode.apply();
            hash_ipv4_flow();
        } else if (hdr.ipv6.isValid()) {
            meta.l3_byte_len = (bit<32>)hdr.ipv6.payloadLength + IPV6_HDR_LEN;
            configure_export_mode.apply();
            hash_ipv6_flow();
        }

        if (hdr.ipv4.isValid() || hdr.ipv6.isValid()) {
            bit<48> now = standard_metadata.ingress_global_timestamp;
            bit<48> last_ts = TS_NEVER;
            bit<1> ts_valid = 1w0;

            last_packet_timestamp.read(last_ts, (bit<32>)0);
            last_ts_valid.read(ts_valid, (bit<32>)0);

            if (ts_valid == 1w1) {
                meta.packet_iat_us = now - last_ts;
            } else {
                meta.packet_iat_us = 0;
            }

            last_packet_timestamp.write((bit<32>)0, now);
            last_ts_valid.write((bit<32>)0, 1w1);

            flow_packet_count.read(meta.current_pkt_count, meta.flow_id);
            flow_byte_count.read(meta.current_byte_count, meta.flow_id);

            bit<48> first_ts = TS_NEVER;
            flow_first_ts.read(first_ts, meta.flow_id);
            if (first_ts == TS_NEVER) {
                flow_first_ts.write(meta.flow_id, now);
                first_ts = now;
            }
            flow_last_ts.write(meta.flow_id, now);

            flow_packet_count.write(meta.flow_id, meta.current_pkt_count + 1);
            flow_byte_count.write(meta.flow_id, meta.current_byte_count + meta.l3_byte_len);

            hdr.telemetry.setValid();
            hdr.telemetry.reserved = 0;
            if (ts_valid == 1w1) {
                hdr.telemetry.flags = 8w1;
            } else {
                hdr.telemetry.flags = 8w0;
            }
            hdr.telemetry.iat_us = meta.packet_iat_us;
            hdr.telemetry.flow_id = meta.flow_id;
            hdr.telemetry.flow_pkt_count = meta.current_pkt_count;
            hdr.telemetry.flow_byte_count = meta.current_byte_count;
            hdr.telemetry.flow_first_ts_us = first_ts;
            hdr.telemetry.flow_last_ts_us = now;

            if (standard_metadata.ingress_port == (bit<9>)1) {
                standard_metadata.egress_spec = (bit<9>)2;
            } else if (standard_metadata.ingress_port == (bit<9>)2) {
                standard_metadata.egress_spec = (bit<9>)1;
            } else {
                mark_to_drop(standard_metadata);
            }
        }
    }
}

control MyEgress(inout headers hdr, inout metadata meta, inout standard_metadata_t standard_metadata) {
    action build_udp_int_report() {
        bit<32> obs_ipv4_src = 0;
        bit<32> obs_ipv4_dst = 0;
        bit<8> obs_ip_proto = 0;
        bit<8> obs_ip_version = 0;
        bit<16> obs_src_port = 0;
        bit<16> obs_dst_port = 0;
        bit<32> obs_l3_len = meta.l3_byte_len;

        bit<8> tele_flags = hdr.telemetry.flags;
        bit<48> tele_iat = hdr.telemetry.iat_us;
        bit<32> tele_flow_id = hdr.telemetry.flow_id;
        bit<32> tele_pkt = hdr.telemetry.flow_pkt_count;
        bit<32> tele_byte = hdr.telemetry.flow_byte_count;
        bit<48> tele_first = hdr.telemetry.flow_first_ts_us;
        bit<48> tele_last = hdr.telemetry.flow_last_ts_us;

        if (hdr.ipv4.isValid()) {
            obs_ip_version = 4;
            obs_ipv4_src = hdr.ipv4.srcAddr;
            obs_ipv4_dst = hdr.ipv4.dstAddr;
            obs_ip_proto = hdr.ipv4.protocol;
        } else if (hdr.ipv6.isValid()) {
            obs_ip_version = 6;
            obs_ip_proto = hdr.ipv6.nextHeader;
        }
        if (hdr.tcp.isValid()) {
            obs_src_port = hdr.tcp.srcPort;
            obs_dst_port = hdr.tcp.dstPort;
        } else if (hdr.udp.isValid()) {
            obs_src_port = hdr.udp.srcPort;
            obs_dst_port = hdr.udp.dstPort;
        }

        hdr.tcp.setInvalid();
        hdr.icmp.setInvalid();
        hdr.ipv6.setInvalid();
        hdr.telemetry.setInvalid();

        hdr.ethernet.dstAddr = COLLECTOR_MAC;
        hdr.ethernet.srcAddr = REPORT_SRC_MAC;
        hdr.ethernet.etherType = 16w0x0800;

        hdr.ipv4.setValid();
        hdr.ipv4.version = 4;
        hdr.ipv4.ihl = 5;
        hdr.ipv4.diffserv = 0;
        hdr.ipv4.totalLen = INT_UDP_PKT_LEN;
        hdr.ipv4.identification = 0;
        hdr.ipv4.flags = 0;
        hdr.ipv4.fragOffset = 0;
        hdr.ipv4.ttl = 64;
        hdr.ipv4.protocol = 17;
        hdr.ipv4.srcAddr = SWITCH_REPORT_IPV4;
        hdr.ipv4.dstAddr = COLLECTOR_IPV4;

        hdr.udp.setValid();
        hdr.udp.srcPort = INT_COLLECTOR_PORT;
        hdr.udp.dstPort = INT_COLLECTOR_PORT;
        hdr.udp.length_ = 8 + INT_REPORT_PAYLOAD_LEN;
        hdr.udp.checksum = 0;

        hdr.int_report.setValid();
        hdr.int_report.magic = INT_REPORT_MAGIC;
        hdr.int_report.flags = tele_flags;
        hdr.int_report.reserved = 0;
        hdr.int_report.iat_us = tele_iat;
        hdr.int_report.flow_id = tele_flow_id;
        hdr.int_report.flow_pkt_count = tele_pkt;
        hdr.int_report.flow_byte_count = tele_byte;
        hdr.int_report.flow_first_ts_us = tele_first;
        hdr.int_report.flow_last_ts_us = tele_last;
        hdr.int_report.ipv4_src = obs_ipv4_src;
        hdr.int_report.ipv4_dst = obs_ipv4_dst;
        hdr.int_report.ip_proto = obs_ip_proto;
        hdr.int_report.ip_version = obs_ip_version;
        hdr.int_report.src_port = obs_src_port;
        hdr.int_report.dst_port = obs_dst_port;
        hdr.int_report.l3_byte_len = obs_l3_len;
    }

    apply {
        if (standard_metadata.instance_type == PKT_INSTANCE_TYPE_EGRESS_CLONE) {
            build_udp_int_report();
        } else if (standard_metadata.egress_port == (bit<9>)2) {
            if (meta.export_mode == 2w0 || meta.export_mode == 2w2) {
                // Keep in-band telemetry trailer on forwarded packets.
            } else {
                hdr.telemetry.setInvalid();
            }
            if (meta.export_mode == 2w1 || meta.export_mode == 2w2) {
                clone(E2E, CLONE_SESSION_INT);
            }
        } else {
            hdr.telemetry.setInvalid();
        }
    }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv, hdr.ipv4.totalLen,
              hdr.ipv4.identification, hdr.ipv4.flags, hdr.ipv4.fragOffset, hdr.ipv4.ttl,
              hdr.ipv4.protocol, hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16
        );
    }
}

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        // v1model deparser: no if/else — emit() is a no-op for invalid headers.
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.ipv6);
        packet.emit(hdr.tcp);
        packet.emit(hdr.udp);
        packet.emit(hdr.icmp);
        packet.emit(hdr.telemetry);
        packet.emit(hdr.int_report);
    }
}

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
