# Finnish Airspace

Home Assistant integration that puts the airspace restrictions in force in Finland on a map, from the NOTAMs Fintraffic
ANS publishes, and fires an event when a new restricted or prohibited area appears.

[![GitHub Release][releases-shield]][releases] [![GitHub Release Date][release-date-shield]][releases] [![HACS][hacs-shield]][hacs] [![License][license-shield]](LICENSE)

<img src="https://raw.githubusercontent.com/jesmak/finnish_airspace/main/docs/images/dashboard-light.png#gh-light-mode-only" width="1280" alt="A map around Tampere with aircraft in their altitude's colours and four airspace areas under them: a new restricted circle selected, a restricted area starting tomorrow drawn faded, and two danger areas in grey. A legend of the altitudes and area types sits over the map, and the list beside it has the restricted area opened to its heights, period, distance and NOTAM, with a NEW tag on its row">
<img src="https://raw.githubusercontent.com/jesmak/finnish_airspace/main/docs/images/dashboard-dark.png#gh-dark-mode-only" width="1280" alt="A map around Tampere with aircraft in their altitude's colours and four airspace areas under them: a new restricted circle selected, a restricted area starting tomorrow drawn faded, and two danger areas in grey. A legend of the altitudes and area types sits over the map, and the list beside it has the restricted area opened to its heights, period, distance and NOTAM, with a NEW tag on its row">

The areas and aircraft in the picture are made up.

## What is it?

A custom component that reads the NOTAMs Fintraffic ANS publishes for the Helsinki FIR and shows the prohibited,
restricted and danger areas they switch on, among them the restricted areas set up at short notice, such as one drawn
around a rescue operation or after an airspace violation near the border. Each area is drawn with its shape from the
Finnish AIP, or with the shape the NOTAM gives itself for a new area, and with its heights, periods and schedule.

The areas come as a **map feed**, one sensor holding every area in force, and those starting within a day, as GeoJSON.
Show it with [map-feed-card](https://github.com/jesmak/map-feed-card) (1.4.0 or newer), on a map of its own or under the
aircraft of an integration such as [ADS-B Live](https://github.com/jesmak/adsb_live). The feed format is documented in
[map-feed-format.md](https://github.com/jesmak/map-feed-card/blob/main/docs/map-feed-format.md).

It covers the whole country, so there is nothing to set up. Each area carries its distance from Home Assistant's home,
so an automation decides what is near.

## Installation

### With HACS

1. Add this repository to HACS custom repositories with type **Integration**
2. Search for Finnish Airspace in HACS and download it
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services

### Manual

1. Download the source code from the latest release
2. Copy the `custom_components/finnish_airspace` folder to your Home Assistant installation's `config/custom_components`
   folder
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services

## Settings

None. The integration is added once and covers all of Finland. Distances are measured from the home location in
Home Assistant's settings.

## Sensors

### The map feed

`sensor.finnish_airspace`'s state is the number of areas on the map. The areas are in the `geojson` attribute in the
[map feed format](https://github.com/jesmak/map-feed-card/blob/main/docs/map-feed-format.md), with a legend and a list
sorted by distance. None of the attributes are recorded in Home Assistant's database, only the count.

An item is the set of areas one NOTAM names, such as the two parts of a range, drawn as one shape. NOTAMs naming the
same areas, such as one for each week of an exercise, are one item with all their periods. The map shows an item while
it is in force and from a day before it starts. An item not in force now is drawn faded.

- **Colours:** prohibited areas red, restricted areas a brick red, danger areas grey, as danger areas (shooting,
  flares, drones) are most of the NOTAMs every week.
- **Name:** the area's name from the AIP (`Kyyvesi`), or its type and codes for an area without one
  (`Restricted area EFR1901`). The list's second line has the codes beside a name, shortened to a range from three parts
  up (`EFD517B–T`), and whether the area is in force or when it starts.
- **NEW:** a restricted or prohibited area whose shape its own NOTAM gives, which is how restrictions set up at short
  notice come, has a NEW tag on its list row.
- **Details:** the heights, with metres beside feet and flight levels, each NOTAM's period, the next windows of its
  schedule, the distance, the NOTAM texts as published, the NOTAM ids and the AIP supplement, and a link to the
  supplement or the NOTAM bulletin.

Times are in Home Assistant's time zone. The texts are in Finnish when Home Assistant's language is Finnish, and in
English otherwise. The NOTAMs stay in English, as published.

Each feature also carries its data for templates and automations, `area_type` (`prohibited`, `restricted` or
`danger`), `codes`, `new_area`, `active`, `active_until`, `next_start`, `distance_km` and `notams`, each with its id,
text, period, `estimated`, schedule, heights and the windows of a schedule that was read.

Beside the feed, four attributes show what didn't fit, so a mismatch shows instead of vanishing:

| Attribute     | What it lists                                                                                                                                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `not_found`   | NOTAMs naming an area found neither in the AIP supplement they refer to nor in ENR 5.1, with its codes. An area whose boundary follows the state border (EFR100, EFD400) is listed here, not drawn, if a NOTAM names it. |
| `without_act` | NOTAMs that name an area without saying `ACT`, such as an aerodrome's notice about what happens while an area is active, in case one is an activation worded some other way.                                             |
| `failed`      | The texts of NOTAMs that didn't parse.                                                                                                                                                                                   |
| `missed`      | The ids of NOTAMs the bulletin's markup hid from the parser.                                                                                                                                                             |

The sensor is unavailable while the bulletin can't be read or has no NOTAMs in it, rather than showing an empty sky.

## Events

`finnish_airspace_new_restriction` fires when a restricted or prohibited area appears in the bulletin for the first
time, whether it is in force yet or not. Danger areas don't fire it. The first update after the integration is added
fires nothing. An area named by its codes is remembered for a week after its last NOTAM ends, so a NOTAM issued again
under a new id doesn't fire again. An area a NOTAM sets up without a code is known only by that NOTAM's id, so a NOTAM
replacing it, to extend it for instance, fires again.

| Field         | Meaning                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------- |
| `notam`       | The id of the item's first NOTAM, such as `A2101/26`                                        |
| `codes`       | The areas' codes                                                                            |
| `names`       | The areas' names from the AIP, if any                                                       |
| `area_type`   | `restricted` or `prohibited`                                                                |
| `new_area`    | Whether the NOTAM gives the area's shape itself                                             |
| `text`        | The NOTAM's text                                                                            |
| `start`       | When the NOTAM starts                                                                       |
| `end`         | When it ends, or null when it is permanent                                                  |
| `estimated`   | Whether the end is an estimate                                                              |
| `schedule`    | The NOTAM's schedule as published, or null                                                  |
| `lower`       | The lower limit, such as `SFC`, or null when neither the NOTAM nor the AIP gives it         |
| `upper`       | The upper limit, such as `2000 ft MSL`, or null when neither the NOTAM nor the AIP gives it |
| `active`      | Whether it is in force now                                                                  |
| `distance_km` | The distance from home to the area's nearest edge, 0 inside it, null without a shape        |

## Examples

Aircraft and airspace areas on one map, framed to the aircraft:

```yaml
type: custom:map-feed-card
list: true
entities:
    - entity: sensor.aircraft_near_tampere
      show_area: true
      labels: true
    - entity: sensor.finnish_airspace
      frame: false
```

A notice when a new restriction appears within 50 km of home:

```yaml
mode: queued
triggers:
    - trigger: event
      event_type: finnish_airspace_new_restriction
conditions:
    - condition: template
      value_template: "{{ trigger.event.data.distance_km is not none and trigger.event.data.distance_km < 50 }}"
actions:
    - action: persistent_notification.create
      data:
          title: New airspace restriction
          message: >-
              {{ (trigger.event.data.codes | join(', ')) or 'A new area' }} {{ trigger.event.data.distance_km }} km away,
              {{ trigger.event.data.lower or '?' }} to {{ trigger.event.data.upper or '?' }}.
              {{ trigger.event.data.text }}
```

## Data

The NOTAMs come from Fintraffic ANS's [pre-flight information bulletin](https://www.ais.fi/en/pre-flight-information-bulletins)
for the Helsinki FIR, and the areas' shapes from the Finnish AIP on [ais.fi](https://www.ais.fi/), ENR 5.1 for the
permanent areas and the AIP supplements for the temporary ones. Fintraffic ANS owns the copyright. By the AIP's section
GEN 0.1, the aeronautical information products are available for further refining and research without a separate fee
or agreement, and only reselling them as such needs one.

The bulletin is updated every half hour and says when next. The integration reads it a few minutes after that, asking
only for a page that has changed, reads ENR 5.1 once a day and each supplement once. The areas read from the AIP are
kept, so a day the AIP can't be reached doesn't empty the map.

Left out:

- Trigger NOTAMs, which announce an area a later NOTAM switches on, and NOTAMs that change an area's limits for good.
- Notices without an area, such as GNSS interference across the FIR.
- The areas in force around the clock, which no NOTAM switches on.

This integration is not affiliated with or endorsed by Fintraffic ANS. It is not for planning or flying a flight.
Check the NOTAMs on ais.fi for that.

## Translating

The texts written into the feed are in `TEXTS` in `map_feed.py`, with the weekdays and months beside it, and Home
Assistant's own texts in `translations/<language>.json`. A new language for the feed needs its texts there, its
number, time and date formats, and its code in `language_of`, all in `map_feed.py`.

## Development

Requires Python 3.14.

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

| Path                           | What it contains                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------- |
| `__init__.py`                  | Setup, and removing the stored memory with the integration                                  |
| `const.py`                     | The addresses, polling times and the event's name                                           |
| `config_flow.py`               | The form, which asks nothing                                                                |
| `coordinator.py`               | Fetching the bulletin, ENR 5.1 and the supplements, storage, polling times and the event    |
| `sensor.py`                    | The map feed sensor                                                                         |
| `bulletin.py`                  | Reading the NOTAM bulletin and what each NOTAM says about areas                             |
| `schedule.py`                  | A NOTAM's schedule as windows within its period                                             |
| `aip.py`                       | Reading ENR 5.1 and the supplements' areas, and heights in one form                         |
| `geometry.py`                  | Coordinates, circles and distances                                                          |
| `feed.py`                      | Matching NOTAMs with areas into items, their activity and heights, and which areas are news |
| `map_feed.py`                  | The items as a map feed, with names, list rows, details, colours, the legend and the texts  |
| `translations/<language>.json` | Home Assistant UI texts                                                                     |

The pictures come from [hass-screenshots](https://github.com/jesmak/hass-screenshots) and `docs/screenshots.json`.

## Support

Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/jesmak)

## License

MIT, see [LICENSE](LICENSE).

[releases-shield]: https://img.shields.io/github/release/jesmak/finnish_airspace.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/jesmak/finnish_airspace?style=for-the-badge
[releases]: https://github.com/jesmak/finnish_airspace/releases
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://hacs.xyz/docs/faq/custom_repositories/
[license-shield]: https://img.shields.io/github/license/jesmak/finnish_airspace.svg?style=for-the-badge
