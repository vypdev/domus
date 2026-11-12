"""Set up or reconfigure the same Domus installation through Home Assistant."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from . import CALENDAR, CONF_PROJECTION, DEADLINES, DOMAIN
from .client import CalendarClient
from .connection import InvalidCredential, InvalidEndpoint, ProjectionUnavailable
from .deadline_client import DeadlineClient


class DomusCalendarFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Verify a connection before accepting an installation-bound entry."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None):
        return await self._configure("user", user_input)

    async def async_step_reconfigure(self, user_input: dict[str, str] | None = None):
        return await self._configure("reconfigure", user_input)

    async def _configure(self, step: str, user_input: dict[str, str] | None):
        entry = self._get_reconfigure_entry() if step == "reconfigure" else None
        errors: dict[str, str] = {}
        if user_input is not None:
            projection = (user_input if entry is None else entry.data).get(
                CONF_PROJECTION, CALENDAR
            )
            try:
                session = async_get_clientsession(self.hass)
                url, token = user_input[CONF_URL], user_input[CONF_TOKEN]
                if projection == DEADLINES:
                    client = DeadlineClient(session, url, token)
                    await client.read()
                    title = f"Domus task deadlines ({client.channel})"
                else:
                    client = CalendarClient(session, url, token)
                    await client.probe(dt_util.utcnow())
                    title = f"Domus ({client.channel})"
            except InvalidEndpoint:
                errors[CONF_URL] = "invalid_endpoint"
            except InvalidCredential:
                errors[CONF_TOKEN] = "invalid_auth"
            except ProjectionUnavailable:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.identity)
                data = {CONF_URL: str(client.url), CONF_TOKEN: user_input[CONF_TOKEN]}
                if projection == DEADLINES:
                    data[CONF_PROJECTION] = DEADLINES
                if entry is None:
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=title, data=data)
                self._abort_if_unique_id_mismatch(reason="wrong_source")
                return self.async_update_reload_and_abort(entry, data_updates=data)
        fields = {
            vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(CONF_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
        if entry is None:
            fields = {
                vol.Optional(CONF_PROJECTION, default=CALENDAR): SelectSelector(
                    SelectSelectorConfig(
                        options=[CALENDAR, DEADLINES], translation_key="projection"
                    )
                ),
                **fields,
            }
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(fields),
                {} if entry is None else {CONF_URL: entry.data[CONF_URL]},
            ),
            errors=errors,
        )
