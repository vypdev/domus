# Home Assistant low-stock sensor qualification

[Domus #128](https://github.com/vypdev/domus/issues/128) qualifies the low-stock
projection in the [Home Assistant surface specification](../../specs/home-assistant-surface.md#show-low-stock-products-in-home-assistant).
The sensor is available through the [Domus companion](../tasks/ha-low-stock-sensor.md).

| Case | Verification |
| --- | --- |
| ha-stock-count-C01 | The protected Overview read and installation query both report 27 eligible products while Overview returns only the first 25 items. |
| ha-stock-count-C02 | Available stock equal to the minimum returns zero. A reservation puts the same product below the threshold even with an outstanding purchase. Repeated reads leave the recorded stock, task, purchase and command facts unchanged. |
| ha-stock-count-C03 | The protected Ingress and standalone tests reject missing, rotated, foreign-installation, cross-channel and wrong-purpose bearers. The stock grant cannot read the calendar or task deadlines. |
| ha-stock-count-C04 | The endpoint is opt-in. Its dedicated setting is absent from default Supervisor options. Existing calendar and deadline entries keep independent access. |
| ha-stock-count-C05 | Disposable Home Assistant Core verifies the native sensor identity through refresh, bearer rotation and process restart. Sensor attributes are limited to Home Assistant metadata. |
| ha-stock-count-C06 | Disposable Core differentiates valid zero from unavailability after a malformed reply, a service failure or a revoked grant. A valid refresh recovers the count, with English and Spanish entity and configuration labels. |
| ha-stock-count-C07 | The container acceptance runs disposable Core against packaged Ingress and HTTPS standalone for separate Edge and Stable identities. The cases use synthetic stock and verify that each sensor returns one count. |

The [artifact declaration](../../addon-edge/artifact.json) records the pinned Edge
runtime, source archive, installed wheel contents and compiled UI. This increment
retains SQLite schema 34. The stock route reads existing records under the
installation's scope, without a schema change or write service.
