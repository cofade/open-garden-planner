"""German and Spanish targets for the living garden (Phase 17 L5, #389)."""

_OBJECTS_DE = {"Garden Light": "Gartenleuchte", "String Lights": "Lichterkette"}
_OBJECTS_ES = {"Garden Light": "Farol de jardín", "String Lights": "Guirnalda de luces"}

DE = {
    "CanvasView": dict(_OBJECTS_DE),
    "GalleryData": dict(_OBJECTS_DE),
    "ObjectType": dict(_OBJECTS_DE),
    "SunSimToolbar": {
        "Animate the plan date through its year at this time of day":
            "Das Plandatum zu dieser Uhrzeit durch sein Jahr abspielen",
        "Fast": "Schnell",
        "Normal": "Normal",
        "Play": "Abspielen",
        "Play the plan date through its year at this time of day":
            "Das Plandatum zu dieser Uhrzeit durch sein Jahr abspielen",
        "Play the time of day; the plan date stays":
            "Die Tageszeit abspielen; das Plandatum bleibt",
        "Slow": "Langsam",
        "Speed": "Geschwindigkeit",
        "The Day": "Den Tag",
        "The Year": "Das Jahr",
    },
    "Workspace": {
        "A clear sky: the sun and its shadows as the plan's sun study has them":
            "Klarer Himmel: Sonne und Schatten wie in der Sonnenstudie des Plans",
        "A grey sky: soft, faint shadows; the sun stays where it is":
            "Grauer Himmel: weiche, schwache Schatten; die Sonne bleibt, wo sie ist",
        "Clear": "Klar",
        "Day": "Tag",
        "Golden hour": "Goldene Stunde",
        "Mood: {mood}": "Stimmung: {mood}",
        "Morning dew": "Morgentau",
        "Night": "Nacht",
        "No forecast for the plan date: today's weather needs the plan date to be today "
        "and a garden location with a forecast.":
            "Keine Vorhersage für das Plandatum: Das heutige Wetter braucht heute als "
            "Plandatum und einen Gartenstandort mit Vorhersage.",
        "Overcast": "Bedeckt",
        "Rain": "Regen",
        "Rain: a grey sky, wet leaves and ground, falling rain":
            "Regen: grauer Himmel, nasse Blätter und nasser Boden, fallender Regen",
        "Show butterflies at the flowers, fireflies on summer evenings and falling leaves "
        "in autumn":
            "Schmetterlinge an den Blüten, Glühwürmchen an Sommerabenden und fallendes Laub "
            "im Herbst zeigen",
        "Snow": "Schnee",
        "Snow on the ground and the leaves, falling snow":
            "Schnee auf dem Boden und den Blättern, fallender Schnee",
        "The forecast's weather while the plan date is today; on any other date a clear sky":
            "Das Wetter der Vorhersage, solange das Plandatum heute ist; an jedem anderen "
            "Datum ein klarer Himmel",
        "Today's Weather": "Heutiges Wetter",
        "Twilight": "Dämmerung",
        "Weather": "Wetter",
        "Weather: Today ({weather})": "Wetter: Heute ({weather})",
        "Weather: {weather}": "Wetter: {weather}",
        "Wildlife and Falling Leaves": "Tiere und fallendes Laub",
    },
}

ES = {
    "CanvasView": dict(_OBJECTS_ES),
    "GalleryData": dict(_OBJECTS_ES),
    "ObjectType": dict(_OBJECTS_ES),
    "SunSimToolbar": {
        "Animate the plan date through its year at this time of day":
            "Animar la fecha del plano a lo largo de su año a esta hora del día",
        "Fast": "Rápida",
        "Normal": "Normal",
        "Play": "Reproducir",
        "Play the plan date through its year at this time of day":
            "Reproducir la fecha del plano a lo largo de su año a esta hora del día",
        "Play the time of day; the plan date stays":
            "Reproducir la hora del día; la fecha del plano no cambia",
        "Slow": "Lenta",
        "Speed": "Velocidad",
        "The Day": "El día",
        "The Year": "El año",
    },
    "Workspace": {
        "A clear sky: the sun and its shadows as the plan's sun study has them":
            "Cielo despejado: el sol y sus sombras como en el estudio solar del plano",
        "A grey sky: soft, faint shadows; the sun stays where it is":
            "Cielo gris: sombras suaves y tenues; el sol se queda donde está",
        "Clear": "Despejado",
        "Day": "Día",
        "Golden hour": "Hora dorada",
        "Mood: {mood}": "Ambiente: {mood}",
        "Morning dew": "Rocío matinal",
        "Night": "Noche",
        "No forecast for the plan date: today's weather needs the plan date to be today "
        "and a garden location with a forecast.":
            "No hay previsión para la fecha del plano: el tiempo de hoy necesita que la "
            "fecha del plano sea hoy y una ubicación del jardín con previsión.",
        "Overcast": "Nublado",
        "Rain": "Lluvia",
        "Rain: a grey sky, wet leaves and ground, falling rain":
            "Lluvia: cielo gris, hojas y suelo mojados, lluvia que cae",
        "Show butterflies at the flowers, fireflies on summer evenings and falling leaves "
        "in autumn":
            "Mostrar mariposas en las flores, luciérnagas en las tardes de verano y hojas "
            "que caen en otoño",
        "Snow": "Nieve",
        "Snow on the ground and the leaves, falling snow":
            "Nieve en el suelo y en las hojas, nieve que cae",
        "The forecast's weather while the plan date is today; on any other date a clear sky":
            "El tiempo de la previsión mientras la fecha del plano sea hoy; en cualquier "
            "otra fecha, un cielo despejado",
        "Today's Weather": "El tiempo de hoy",
        "Twilight": "Crepúsculo",
        "Weather": "Tiempo",
        "Weather: Today ({weather})": "Tiempo: hoy ({weather})",
        "Weather: {weather}": "Tiempo: {weather}",
        "Wildlife and Falling Leaves": "Fauna y hojas que caen",
    },
}
