---
title: Zehnder ComfoConnect PRO
description: Instructions on how to integrate a Zehnder ComfoAir Q or Flex ventilation unit with Home Assistant through the ComfoConnect PRO gateway over Modbus.
ha_category:
  - Climate
  - Fan
  - Modbus-controlled
  - Sensor
ha_release: 2026.11
ha_iot_class: Local Polling
ha_codeowners:
  - '@AlCalzone'
ha_domain: comfoconnect_pro
ha_platforms:
  - binary_sensor
  - button
  - diagnostics
  - fan
  - number
  - select
  - sensor
  - switch
ha_config_flow: true
ha_integration_type: device
ha_quality_scale: bronze
---

The **Zehnder ComfoConnect PRO** {% term integration %} connects Home Assistant to a Zehnder ComfoAir Q or ComfoAir Flex ventilation unit through the ComfoConnect PRO gateway. It talks to the gateway over Modbus TCP on your network, or over Modbus RTU on its RS-485 terminals.

It reads the airflow, the temperature and humidity of each air stream, the CO₂ levels and the filter status, and lets you change the fan speed, boost, away mode and the temperature profile.

## Use cases

- Boosting the ventilation while you shower or cook. An automation turns on **Boost** when a bathroom humidity sensor rises.
- Lowering the ventilation while nobody is home. Turn on **Away** when the last person leaves.
- Following CO₂ in each room. Each CO₂ zone wired to the unit becomes a sensor.
- Knowing when to change the filters. **Filter days remaining** counts down, and the **Filter** sensor turns on when the filters are due.

## Supported devices

The integration supports the Zehnder ComfoConnect PRO gateway (product number 30006323) connected over ComfoNet to a ComfoAir Q or ComfoAir Flex ventilation unit.

## Unsupported devices

- The older ComfoConnect LAN C gateway. Use the [Zehnder ComfoAir Q](/integrations/comfoconnect/) integration for it.
- ComfoAir Classic units (ComfoAir 160 to 550, SL and Standard models). The gateway connects to them, but it serves Modbus only for the ComfoAir Q and Flex.

## Prerequisites

1. Open the gateway's web interface, for example at `http://comfoconnectpro.local`.
2. On the **Protocols and services** page, select **Modbus TCP** or **Modbus RTU**.
3. Note the unit ID. The default is `1`.
4. For Modbus TCP, note the gateway's IP address from the **Network** page. For Modbus RTU, note the baud rate and parity, and wire the gateway's terminals A and B to your RS-485 adapter.

{% include integrations/config_flow.md %}

First choose how Home Assistant reaches the gateway: **Network (Modbus TCP)** or **Serial port (Modbus RTU)**.

{% configuration_basic %}
Host:
  description: "Modbus TCP only. The hostname or IP address of the gateway."
Port:
  description: "Modbus TCP only. The Modbus TCP port. The gateway uses `502`."
Serial port:
  description: "Modbus RTU only. The serial port wired to the gateway's RS-485 terminals. Ports shared over the network by a serial proxy, such as an ESPHome device, are listed too."
Baud rate:
  description: "Modbus RTU only. The baud rate set on the gateway."
Parity:
  description: "Modbus RTU only. The parity set on the gateway. The default is even. Without parity, the gateway uses 2 stop bits, and the integration matches that."
Modbus unit ID:
  description: "The unit ID set on the gateway. The default is `1`."
{% endconfiguration_basic %}

The integration checks that the gateway reaches a supported ventilation unit before it creates the entry.

{% note %}
Home Assistant can share a Modbus connection between integrations. Another integration that already talks to the same gateway or serial port shares the connection instead of opening a second one.
{% endnote %}

## Reconfiguration

If the gateway gets a new IP address, you change its serial settings, or you move it between the network and RS-485, you can update it without removing the integration:

1. Go to {% my integrations title="**Settings** > **Devices & services**" %} and find the **Zehnder ComfoConnect PRO** integration.
2. Select the three-dot menu {% icon "mdi:dots-vertical" %} and choose **Reconfigure**.
3. Choose **Network (Modbus TCP)** or **Serial port (Modbus RTU)**.
4. Update the settings, then select **Submit**.

When two gateways share one RS-485 bus, they also share its baud rate and parity. Reconfiguring one of them to new line settings fails with **Failed to connect**, because the other entry still holds the bus with the old ones. To change the line settings of both:

1. Disable the second entry.
2. Reconfigure the first entry to the new settings.
3. Enable the second entry and reconfigure it to the same settings.

## Supported functionality

All entities belong to one device, named after the config entry.

### Fan

The fan sets the ventilation speed. Its four speeds are the unit's presets: away (25 %), low (50 %), medium (75 %) and high (100 %). The **Auto** preset hands the speed to the unit's own control. Choosing a speed turns auto mode off.

The unit always ventilates, so the fan cannot be turned off.

### Sensors

- **Airflow**: in m³/h.
- **Room temperature**, **Extract air temperature**, **Exhaust air temperature**, **Outdoor air temperature**, **Supply air temperature**. Extract air comes from the rooms into the unit. Exhaust air leaves the house. Supply air goes into the rooms.
- The humidity of the same five air streams.
- **CO₂ zone 1** to **CO₂ zone 8**: added once a zone reports a level.
- **Filter days remaining**.
- **Active error 1** to **Active error 5** (diagnostic): the alarms the unit reports, by name. Only the first is enabled by default.

### Binary sensors

- **Filter**: on when the filters must be replaced.
- **Error** (diagnostic): on while any alarm is active.
- **Standby**: on while the unit is in standby.
- **ComfoHood**: on while the ComfoHood cooker hood runs.

### Switches

- **Boost**: runs the fans at boost speed for the **Boost duration**.
- **Away**: the unit's away function.
- **ComfoCool**: allows the ComfoCool unit to cool.

### Configuration

- **Temperature profile** (select): normal, cold or warm. It applies in the adaptive and fixed profile modes.
- **Temperature profile mode** (select): adaptive, fixed, or external setpoint.
- **External setpoint** (number): the comfort temperature in the external setpoint mode.
- **Boost duration** (number): in seconds, up to 65534, or exactly 86400 for 24 hours.
- **Reset errors** (button): clears the unit's alarms.

## Examples

### Boost while the bathroom is humid

```yaml
automation:
  - alias: "Boost ventilation after a shower"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.bathroom_humidity
        above: 75
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.comfoair_boost
```

### Away mode while nobody is home

```yaml
automation:
  - alias: "Ventilation away mode"
    triggers:
      - trigger: state
        entity_id: zone.home
        to: "0"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.comfoair_away
```

## Data updates

The integration polls the gateway every 30 seconds. One poll makes five Modbus reads. A write is followed by an early poll, so the state updates right away.

If one block of registers fails to read, only the entities from that block become unavailable. If the gateway loses its ventilation unit, all entities become unavailable until it finds the unit again.

## Known limitations

- The gateway has no serial number over Modbus. The integration tells gateways apart by host and port, or by serial port and unit ID. The same gateway added once by IP address and once by hostname shows up twice.
- Two gateways behind one Modbus TCP-to-RTU converter, on different unit IDs, cannot both be added. The integration identifies a TCP gateway by host and port only.
- The ventilation unit cannot be turned off or put into standby over Modbus.
- The manual does not say what a CO₂ zone without a sensor reports. The integration takes 0 to mean no sensor.
- The manual gives no range for the external setpoint. The integration allows 0 to 40 °C.

## Troubleshooting

### The gateway does not reach a ventilation unit

The gateway answered, but it reports a connection state other than OK:

- **30**: the unit on ComfoNet is not a ComfoAir Q or Flex.
- **40**: the unit's firmware is not compatible with the gateway. Update the unit's firmware.
- **50**: the gateway finds no unit. Check the ComfoNet cable.

### Failed to connect

- Check that Modbus TCP or Modbus RTU is selected on the gateway's **Protocols and services** page, and that it matches what you chose in Home Assistant.
- Check the unit ID.
- For Modbus RTU, check the baud rate, the parity, and the A and B wiring.

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service_steps.md %}

After removing the integration, set the gateway's protocol back to **None** if nothing else uses Modbus.
