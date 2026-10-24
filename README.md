# Finnish Airspace

The airspace restrictions in force in Finland, on a map in Home Assistant.

## What is it?

A Home Assistant integration that reads the NOTAMs Fintraffic ANS publishes for the Helsinki FIR and shows the
prohibited, restricted and danger areas they switch on, including areas set up at short notice. The areas are drawn
by [map-feed-card](https://github.com/jesmak/map-feed-card), and a new restricted or prohibited area fires an event for
automations. It covers the whole country, so there is nothing to set up.

It is under construction and not released yet.

## Data

The NOTAMs come from Fintraffic ANS's [pre-flight information bulletins](https://www.ais.fi/en/pre-flight-information-bulletins),
and the areas' shapes from the Finnish AIP (ENR 5.1 and the AIP supplements) on [ais.fi](https://www.ais.fi/).
Fintraffic ANS owns the copyright. By the AIP's section GEN 0.1, the aeronautical information products are available
for further refining and research without a separate fee or agreement, and only reselling them as such needs one.

This integration is not affiliated with or endorsed by Fintraffic ANS. It is not for planning or flying a flight.
Check the NOTAMs on ais.fi for that.

## License

MIT
