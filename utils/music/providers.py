"""Central registry for Lavalink/LavaSrc search providers.

Keep source-manager names, search prefixes and partial-track templates in one place.
The registry intentionally contains search-capable sources only; URL-only sources
are handled by Lavalink's URL resolver and are not exposed as manual search choices.
"""

PROVIDER_SPECS = {
    "deezer": {
        "prefix": "dzsearch",
        "managers": ("deezer",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("dzisrc:{isrc}", "dzsearch:{title} - {author}"),
    },
    "soundcloud": {
        "prefix": "scsearch",
        "managers": ("soundcloud",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("scsearch:{title} - {author}",),
    },
    "bandcamp": {
        "prefix": "bcsearch",
        "managers": ("bandcamp",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("bcsearch:{title} - {author}",),
    },
    "jiosaavn": {
        "prefix": "jssearch",
        "managers": ("jiosaavn",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("jssearch:{title} - {author}",),
    },
    "spotify": {
        "prefix": "spsearch",
        "managers": ("spotify",),
        "auto_add": True,
        "native_only": False,
        "partial": ("spsearch:{title} - {author}",),
    },
    "tidal": {
        "prefix": "tdsearch",
        "managers": ("tidal",),
        "auto_add": True,
        "native_only": False,
        "partial": ("tdsearch:{title} - {author}",),
    },
    "applemusic": {
        "prefix": "amsearch",
        "managers": ("applemusic",),
        "auto_add": True,
        "native_only": False,
        "partial": ("amsearch:{title} - {author}",),
    },
    "youtube": {
        "prefix": "ytmsearch",
        "managers": ("youtube",),
        "auto_add": False,
        "native_only": True,
        "partial": ('ytmsearch:"{isrc}"', 'ytmsearch:"{title} - {author}"'),
    },
    "ytdlp": {
        "prefix": "ytsearch",
        "managers": ("ytdlp",),
        "auto_add": False,
        "native_only": True,
        "direct_playback": True,
        "partial": ('ytsearch:"{isrc}"', 'ytsearch:"{title} - {author}"'),
    },
    "yandexmusic": {
        "prefix": "ymsearch",
        "managers": ("yandexmusic",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("ymsearch:{title} - {author}",),
    },
    "vkmusic": {
        "prefix": "vksearch",
        "managers": ("vkmusic",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("vksearch:{title} - {author}",),
    },
    "qobuz": {
        "prefix": "qbsearch",
        "managers": ("qobuz",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("qbisrc:{isrc}", "qbsearch:{title} - {author}"),
    },
    "amazonmusic": {
        "prefix": "amzsearch",
        "managers": ("amazonmusic",),
        "auto_add": True,
        "native_only": False,
        "partial": ("amzsearch:{title} - {author}",),
    },
    "audiomack": {
        "prefix": "admsearch",
        "managers": ("audiomack",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("admsearch:{title} - {author}",),
    },
    "audius": {
        "prefix": "audsearch",
        "managers": ("audius",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("audsearch:{title} - {author}",),
    },
    "jamendo": {
        "prefix": "jamsearch",
        "managers": ("jamendo",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("jamsearch:{title} - {author}",),
    },
    "ccmixter": {
        "prefix": "ccsearch",
        "managers": ("ccmixter",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("ccsearch:{title} - {author}",),
    },
    "gaana": {
        "prefix": "gnsearch",
        "managers": ("gaana",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("gnsearch:{title} - {author}",),
    },
    "bilibili": {
        "prefix": "bilisearch",
        "managers": ("bilibili",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("bilisearch:{title} - {author}",),
    },
    "internetarchive": {
        "prefix": "iasearch",
        "managers": ("internetarchive", "internet-archive"),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("iasearch:{title} - {author}",),
    },
    "googledrive": {
        "prefix": "dvsearch",
        "managers": ("googledrive", "google-drive"),
        "auto_add": False,
        "native_only": True,
        "direct_playback": True,
        "partial": ("dvsearch:{title} - {author}",),
    },
    "pornhub": {
        "prefix": "phsearch",
        "managers": ("pornhub",),
        "auto_add": True,
        "native_only": True,
        "direct_playback": True,
        "partial": ("phsearch:{title} - {author}",),
    },
}

# Aliases used by Lavalink plugin metadata and older source-manager versions.
SOURCE_PROVIDER_PREFIX = {
    source: spec["prefix"]
    for source, spec in PROVIDER_SPECS.items()
}
SOURCE_PROVIDER_PREFIX.update({
    "google-drive": "dvsearch",
    "internet-archive": "iasearch",
})

PROVIDER_PREFIX_BY_SOURCE = SOURCE_PROVIDER_PREFIX

# Explicit LavaSrc query schemes must bypass the bot's default search prefix.
EXPLICIT_QUERY_PREFIXES = tuple(
    f"{spec['prefix']}:" for spec in PROVIDER_SPECS.values()
) + (
    "dzisrc:",
    "sprec:",
    "dzrec:",
    "jsrec:",
    "ymrec:",
    "vkrec:",
    "tdrec:",
    "qbisrc:",
    "qbrec:",
    "gntrending:",
    "gncharts:",
    "gnreleases:",
    "gnalbums:",
    "ftts://",
    "speak:",
)


def is_explicit_lavasrc_query(query):
    return query.lower().startswith(EXPLICIT_QUERY_PREFIXES)


# Direct URL resolvers without a text-search prefix.
URL_ONLY_DIRECT_SOURCES = {
    "getyarn": ("get-yarn", "getyarn"),
    "clypit": ("clypit",),
    "elgato": ("elgato",),
    "pixeldrain": ("pixeldrain",),
    "tumblr": ("tumblr",),
}


def sync_node_providers(node):
    """Reconcile configured providers with source managers reported by Lavalink."""
    available_managers = set(node.info.get("sourceManagers") or ())
    configured = set(node.original_providers or ())
    native_only = bool(node.only_use_native_search_providers)

    providers = []
    partial = []

    # Preserve custom providers that are not managed by this registry.
    managed_prefixes = {spec["prefix"] for spec in PROVIDER_SPECS.values()}
    providers.extend(p for p in node.original_providers if p not in managed_prefixes)

    for source, spec in PROVIDER_SPECS.items():
        prefix = spec["prefix"]
        manager_available = any(manager in available_managers for manager in spec["managers"])
        allowed = not native_only or spec["native_only"]

        # YouTube search prefixes remain opt-in through SEARCH_PROVIDERS.
        should_enable = prefix in configured or spec["auto_add"]
        if manager_available and allowed and should_enable:
            if prefix not in providers:
                providers.append(prefix)
            for query in spec["partial"]:
                if query not in partial:
                    partial.append(query)

    node.search_providers = providers
    node.partial_providers = partial

    # Direct-playback LavaSrc managers can resolve their own partial-track URLs.
    for source, spec in PROVIDER_SPECS.items():
        if not spec.get("direct_playback"):
            continue
        manager_available = any(manager in available_managers for manager in spec["managers"])
        if manager_available:
            node.native_sources.add(source)
            node.native_sources.update(spec["managers"])
        else:
            if source not in {"soundcloud", "bandcamp"}:
                node.native_sources.discard(source)
            for manager in spec["managers"]:
                if manager not in {"youtube", "soundcloud", "bandcamp"}:
                    node.native_sources.discard(manager)

    # Direct URL resolvers without search prefixes still need native resolution.
    for source, managers in URL_ONLY_DIRECT_SOURCES.items():
        manager_available = any(manager in available_managers for manager in managers)
        if manager_available:
            node.native_sources.add(source)
            node.native_sources.update(managers)
        else:
            node.native_sources.discard(source)
            for manager in managers:
                node.native_sources.discard(manager)

    # LavaSrc's "youtube" manager is YouTube Music search-only. Actual
    # YouTube playback belongs to the separate yt-dlp source.
    if "youtube" in available_managers and "ytdlp" not in available_managers:
        node.native_sources.discard("youtube")

    return providers
