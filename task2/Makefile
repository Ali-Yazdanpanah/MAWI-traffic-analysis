P4C ?= p4c
# simple_switch exposes Thrift (9090) for register_reset / simple_switch_CLI.
# simple_switch_grpc only exposes gRPC (50051) in the p4c image — no Thrift listener.
BMV2_SWITCH_EXE ?= simple_switch
RUN_SCRIPT ?= utils/run_exercise.py

P4SRC := p4src/task2.p4
TOPOLOGY := topo/topology.json

BUILD_DIR := build
PCAP_DIR := pcaps
LOG_DIR := logs
P4JSON := $(BUILD_DIR)/task2.json
P4INFO := $(BUILD_DIR)/task2.p4.p4info.txtpb

.PHONY: all build run-thrift run-grpc stop clean clean-artifacts dirs trace trace-prepare test-mawi reset reset-grpc read-registers read-registers-grpc plot

all: build

build: dirs $(P4JSON)

# p4c treats -o as an output *directory*; passing build/task2.json creates
# build/task2.json/task2.json and breaks Mininet (expects a file path).
$(P4JSON): $(P4SRC)
	$(P4C) --target bmv2 --arch v1model --p4runtime-files $(P4INFO) -o $(BUILD_DIR) $<

run-thrift: build
	sudo PATH=$(PATH) python3 $(RUN_SCRIPT) -t $(TOPOLOGY) -j $(P4JSON) -b $(BMV2_SWITCH_EXE)

# Homework gRPC target (P4Runtime on 50051; use controller_grpc.py / read_registers_grpc.py)
run-grpc: build
	sudo PATH=$(PATH) python3 $(RUN_SCRIPT) -t $(TOPOLOGY) -j $(P4JSON) -b simple_switch_grpc

reset:
	sudo python3 control_plane/controller_thrift.py

reset-grpc:
	sudo python3 control_plane/controller_grpc.py

read-registers:
	python3 control_plane/read_registers_thrift.py --output data/registers.json

read-registers-grpc:
	python3 control_plane/read_registers_grpc.py --output data/registers_grpc.json

stop:
	sudo mn -c 2>/dev/null || true
	-sudo pkill -TERM -f '[s]imple_switch' 2>/dev/null || true
	@sleep 0.5
	-sudo pkill -KILL -f '[s]imple_switch' 2>/dev/null || true

clean: stop
	@echo "Removing $(BUILD_DIR)/, $(PCAP_DIR)/, $(LOG_DIR)/ ..."
	sudo rm -rf $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)
	@$(MAKE) --no-print-directory dirs

dirs:
	mkdir -p $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR) data

# Decompress repo-root 201302011400.dump.gz -> data/mawi_<N>.pcap (default N=10000)
PACKET_LIMIT ?= 10000
REPLAY_MULTIPLIER ?= 0.001
trace-prepare:
	chmod +x scripts/prepare_trace.sh scripts/replay_on_h1.sh scripts/capture_on_h2.sh scripts/test_mawi.sh
	PACKET_LIMIT=$(PACKET_LIMIT) bash scripts/prepare_trace.sh

# Replay MAWI capture test (Mininet must be running: make run-thrift or make run-grpc in another terminal).
# Override rate: REPLAY_MULTIPLIER=0.001 make test-mawi
# Legacy tcpdump capture: CAPTURE_MODE=pcap make test-mawi
# UDP INT export: CAPTURE_MODE=udp CAPTURE_USE_GRPC=1 make test-mawi
# BMv2 switch pcap: CAPTURE_MODE=switch make test-mawi
#   or: CAPTURE_MODE=pcap CAPTURE_SOURCE=switch make test-mawi
CAPTURE_MODE ?= live
CAPTURE_SOURCE ?= h2
CAPTURE_TIMEOUT ?= 300
CAPTURE_USE_GRPC ?= 0
INT_UDP_PORT ?= 4790
SWITCH_PCAP ?= pcaps/s1-eth2_out.pcap
test-mawi:
	chmod +x scripts/test_mawi.sh
	sed -i 's/\r$$//' scripts/test_mawi.sh
	sudo PACKET_LIMIT=$(PACKET_LIMIT) REPLAY_MULTIPLIER=$(REPLAY_MULTIPLIER) \
		CAPTURE_MODE=$(CAPTURE_MODE) CAPTURE_SOURCE=$(CAPTURE_SOURCE) \
		CAPTURE_TIMEOUT=$(CAPTURE_TIMEOUT) \
		CAPTURE_USE_GRPC=$(CAPTURE_USE_GRPC) INT_UDP_PORT=$(INT_UDP_PORT) \
		SWITCH_PCAP=$(SWITCH_PCAP) \
		bash scripts/test_mawi.sh

trace: trace-prepare
	@echo "Prepared data/replay.pcap — start 'make run-thrift' or 'make run-grpc', reset registers, then replay (see docs/RUN_WITH_MAWI.md)"

# Task I-identical charts from data/capture.jsonl -> results/n_<N>/plots/
plot:
	python3 control_plane/pipeline_capture_jsonl.py --capture-jsonl data/capture.jsonl -n $(PACKET_LIMIT)

# Remove regenerable outputs (also: ../scripts/clean_artifacts.sh from repo root)
clean-artifacts:
	rm -rf build pcaps logs build-test
	find control_plane utils -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
