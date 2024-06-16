from collections import defaultdict

from modules.phrasey.environments.environment import Environment, JsonFormat

system = """

"""

ENTITY_GLOSSARY = {
    "player": "As a player, you are a mighty adventurer in the blocky realms of Minecraft. Armed with creativity and determination, you shape the world around you and conquer its challenges.",
    "pillager": "Pillagers, those rough and rowdy troublemakers, are always spoiling for a fight. With their menacing demeanor and threatening remarks, they're the last mob you want to encounter on a raid.",
    "zombie": "Zombies, the relentless undead, stumble through the night in search of their next meal. Moaning and groaning, they're not the most conversational bunch, but they sure are persistent.",
    "creeper": "Creepers, the explosive green menaces, are the masters of surprise. With a hiss and a bang, they make their presence known, leaving destruction in their wake.",
    "enderman": "Endermen, the enigmatic wanderers of the End, are as mysterious as they are dangerous. With their teleportation antics and piercing gaze, they command both fear and fascination.",
    "skeleton": "Skeletons, the sharpshooters of the night, take aim with deadly precision. With bones as brittle as their resolve, they're not afraid to take potshots at any unsuspecting traveler.",
    "endermite": "Endermites, the tiny terrors spawned from teleportation mishaps, scuttle about in search of mischief. Though small in stature, they pack a punch when provoked.",
    "blaze": "Blazes, the fiery denizens of the Nether, guard their domain with flaming ferocity. With fireballs at the ready, they're quick to turn intruders into toast.",
    "ghast": "Ghasts, the wailing specters of the Nether, haunt its fiery depths with their explosive temperaments. With cries that chill the bone, they rain destruction from above.",
    "zombie_pigman": "Zombie pigmen, the grizzled veterans of the Nether, roam its caverns in search of vengeance. With swords in hand and grudges to settle, they're not to be trifled with.",
    "wither_skeleton": "Wither skeletons, the cursed warriors of the Nether, stalk its corridors with grim determination. With skulls aglow and blades at the ready, they strike fear into the hearts of mortals.",
    "stray": "Strays, the icy sentinels of the tundra, lurk in the frosty night. With frostbitten arrows and hearts as cold as ice, they're a chilling reminder of nature's wrath.",
    "husk": "Husks, the desiccated horrors of the desert, shamble through the dunes in search of sustenance. With hunger in their eyes and sand in their veins, they're always on the hunt.",
    "vindicator": "Vindicators, the axe-wielding enforcers of the woodland mansions, guard their territory with ruthless efficiency. With a swing and a chop, they make short work of any who dare intrude.",
    "evoker": "Evokers, the sinister spellcasters of the Illagers, weave dark magic with malevolent glee. With a flick of the wrist and a chant of doom, they summon forth horrors from beyond.",
    "vex": "Vexes, the vexing minions of the Evokers, dart through the air with malicious intent. With sharp talons and ethereal forms, they're a nightmare to behold.",
    "shulker": "Shulkers, the shell-dwelling defenders of the End cities, lurk in their floating fortresses with silent vigilance. With homing projectiles and resilient shells, they're a challenge to overcome.",
    "drowned": "Drowned, the sunken husks of the deep, haunt the ocean depths with silent menace. With seaweed-strewn hair and waterlogged limbs, they're a reminder of the perils that lie beneath.",
    "phantom": "Phantoms, the spectral terrors of the night sky, swoop down on unsuspecting prey with eerie precision. With wings of shadow and cries of despair, they're a haunting presence in the darkness.",
    "guardian": "Guardians, the aquatic sentinels of the ocean monuments, defend their ancient domains with lethal force. With laser-like focus and impenetrable scales, they're a formidable foe to face.",
    "elder_guardian": "Elder guardians, the ancient titans of the ocean depths, command respect from all who dare to approach. With age comes wisdom, and with wisdom comes the power to crush any who oppose them.",
    "hoglin": "Hoglins, the brutish boars of the crimson forests, snort and snarl as they patrol their territory. With tusks as sharp as their tempers, they're not to be underestimated.",
    "piglin": "Piglins, the wary wanderers of the Nether wastes, eye intruders with suspicion and greed. With goldlust in their hearts and swords at the ready, they're always on the lookout for treasure.",
    "spider": "Spiders, the eight-legged hunters of the night, skitter through the shadows with predatory intent. With fangs of venom and eyes of malice, they're a terror to behold.",
    "zoglin": "Zoglins, the twisted remnants of the hoglins, roam the Nether wastes with reckless abandon. With feral grunts and wild eyes, they're a danger to anything foolish enough to cross their path.",
    "ender_dragon": "Ender dragons, the ancient overlords of the End, rule their domain with unchallenged authority. With wings of shadow and breath of darkness, they're a force to be reckoned with.",
    "wither": "Withers, the unholy abominations of the underworld, bring destruction in their wake. With skulls of bone and souls of flame, they're a nightmare made real.",
    "iron_golem": "Iron golems, the stalwart guardians of the villages, stand watch with silent vigilance. With hearts of iron and fists of steel, they're a beacon of hope in a world besieged by darkness.",
    "snow_golem": "Snow golems, the friendly protectors of the frosty wastes, trundle through the snow with cheerful abandon. With hearts of ice and faces of joy, they're a welcome sight on a cold winter's day.",
    "bee": "Bees, the buzzing pollinators of the meadows, flit from flower to flower with industrious zeal. With wings of gold and stingers of fury, they're a vital part of the natural world.",
    "cat": "Cats, the purring hunters of the night, prowl through the shadows with graceful precision. With eyes of emerald and claws of steel, they're both friend and foe to the creatures of the night.",
    "fox": "Foxes, the cunning tricksters of the forest, dart through the underbrush with sly intent. With tails of flame and hearts of mischief, they're always one step ahead of their prey.",
    "panda": "Pandas, the playful giants of the bamboo groves, roll and tumble with carefree abandon. With fur of black and white and hearts of joy, they're a symbol of harmony and peace.",
    "polar_bear": "Polar bears, the fierce defenders of the icy wastes, roam the frozen tundra with stoic determination. With claws of ice and roars of thunder, they're a force to be reckoned with.",
    "wolf": "Wolves, the loyal companions of the wilderness, run with the pack and fight with the fury of the wild. With eyes of amber and fangs of steel, they're the ultimate hunters of the night.",
    "ocelot": "Ocelots, the elusive hunters of the jungle, stalk through the undergrowth with silent grace. With coats of gold and eyes of jade, they're the masters of stealth and cunning.",
    "mooshroom": "Mooshrooms, the gentle giants of the mushroom fields, graze on the fungi with contented sighs. With coats of crimson and milk of white, they're a living reminder of nature's bounty.",
    "llama": "Llamas, the steadfast pack animals of the Andes, trek through the mountains with steady determination. With backs of wool and hearts of gold, they're a traveler's best friend.",
    "trader_llama": "Trader llamas, the caravan companions of the wandering merchants, bear their burdens with silent grace. With packs of goods and eyes of wisdom, they're a reliable source of trade and treasure.",
    "horse": "Horses, the swift steeds of the plains, gallop through the grasslands with the wind in their manes. With hooves of thunder and hearts of fire, they're the champions of the open road.",
    "donkey": "Donkeys, the sturdy pack animals of the hills, plod along with patient determination. With ears of silk and backs of stone, they're the unsung heroes of the trade routes.",
    "mule": "Mules, the hardy hybrids of the highlands, carry their burdens with stoic resolve. With strength of earth and spirit of sky, they're a testament to the endurance of the wilderness.",
    "skeleton_horse": "Skeleton horses, the spectral steeds of the night, gallop through the darkness with silent grace. With bones of ivory and eyes of shadow, they're a haunting reminder of the world beyond.",
    "zombie_horse": "Zombie horses, the cursed chargers of the undead, shuffle through the night with hollow eyes. With flesh of rot and breath of decay, they're a grim omen of things to come.",
    "chicken": "Chickens, the clucking denizens of the coop, scratch and peck with carefree abandon. With feathers of gold and eggs of plenty, they're a staple of farm life the world over.",
    "cow": "Cows, the gentle giants of the pasture, graze on the grass with contented sighs. With hides of brown and milk of white, they're a symbol of abundance and prosperity.",
    "pig": "Pigs, the oinking wanderers of the barnyard, root and snuffle with gleeful abandon. With snouts of pink and hearts of curiosity, they're a joy to behold.",
    "sheep": "Sheep, the woolly wonders of the meadow, graze on the grass with peaceful serenity. With coats of every hue and eyes of innocence, they're a living rainbow in a world of green.",
    "rabbit": "Rabbits, the hopping denizens of the warren, dart through the underbrush with nimble grace. With ears of velvet and noses of twitching, they're a symbol of fertility and rebirth.",
    "squid": "Squids, the ink-spewing denizens of the deep, glide through the ocean with silent grace. With tentacles of silk and ink of black, they're a mysterious presence in the watery depths.",
    "bat": "Bats, the winged guardians of the cave, flit through the darkness with silent vigilance. With wings of leather and eyes of night, they're a symbol of the unseen world that lies beneath.",
    "cod": "Cod, the silvery denizens of the sea, dart through the water with shimmering grace. With scales of silver and fins of glass, they're a staple of oceanic life the world over.",
    "salmon": "Salmon, the leaping wonders of the river, swim against the current with determined grace. With bodies of pink and hearts of steel, they're a testament to the power of perseverance.",
    "tropical_fish": "Tropical fish, the colorful dancers of the coral reefs, flit through the water with vibrant grace. With fins of every hue and scales of rainbow, they're a living canvas in a world of blue.",
    "pufferfish": "Pufferfish, the spiky sentinels of the sea, puff up with defensive fury when threatened. With spines of venom and eyes of caution, they're a warning to all who would dare disturb them.",
    "turtle": "Turtles, the ancient mariners of the ocean, plod along with patient determination. With shells of stone and hearts of wisdom, they're a symbol of longevity and resilience.",
    "dolphin": "Dolphins, the playful acrobats of the sea, leap through the waves with joyous abandon. With clicks of laughter and eyes of mischief, they're a welcome sight to sailors the world over.",
    "axolotl": "Axolotls, the amphibious wonders of the underground rivers, dart through the water with graceful abandon. With gills of silver and eyes of wonder, they're a testament to the beauty of the subterranean world.",
    "glow_squid": "Glow squids, the bioluminescent beauties of the ocean depths, shimmer with otherworldly grace. With bodies of light and eyes of wonder, they're a beacon of hope in the darkness.",
    "goat": "Goats, the agile climbers of the mountains, bound through the crags with fearless abandon. With horns of ivory and hearts of courage, they're a symbol of strength and determination.",
    "wandering_trader": "Wandering traders, the nomadic merchants of the land, ply their trade with boundless enthusiasm. With packs of goods and tales of adventure, they're a welcome sight to weary travelers.",
    "villager": "Villagers, the industrious denizens of the town, go about their daily lives with cheerful determination. With hearts of gold and hands of skill, they're the backbone of civilization in a world of endless possibilities.",
    "witch": "Witches, the mysterious practitioners of the dark arts, brew their potions with sinister glee. With cauldrons of bubbling brew and cackles of laughter, they're a force to be reckoned with.",
    "illusioner": "Illusioners, the spectral tricksters of the nether, weave their spells with deceptive grace. With illusions of shadow and mirrors of deceit, they're a challenge to both mind and body.",
    "piglin_brute": "Piglin brutes, the brutish enforcers of the nether wastes, patrol their territory with ruthless efficiency. With tusks of iron and tempers of flame, they're a formidable foe to all who dare oppose them.",
    "wither_rose": "Wither roses, the cursed blooms of the underworld, spread their thorny tendrils with malicious intent. With petals of darkness and thorns of despair, they're a blight upon the land.",
}

HEALTH_GLOSSARY = {
    "low": "Your are on the brink of death.",
    "medium": "You are injured, but you can still fight.",
    "high": "You are in good health.",
    "burning": "You are burning!",
    "freezing": "You are freezing!",
}

TARGET_HEALTH_GLOSSARY = {
    "low": "The target is injured, their health is low.",
    "medium": "The target is injured, but they can still fight.",
    "high": "The target is in good health.",
    "burning": "The target is burning!",
    "freezing": "The target is freezing!",
}

BIOME_GLOSSARY = {
    "desert": "You are in a desert biome, a hot and dry place with little vegetation.",
}

WEATHER_GLOSSARY = {
    "clear": "The weather is clear, the sun is shining.",
    "rain": "It is raining.",
    "thunderstorm": "There is a thunderstorm.",
    "snow": "It is snowing.",
}

TIME_GLOSSARY = {
    "day": "It is day.",
    "night": "It is night.",
    "dawn": "It is dawn.",
    "dusk": "It is dusk.",
}

LIGHT_GLOSSARY = {
    "dim": "It is dim.",
    "artificial": "Only artificial light brightens the area.",
    "dark": "It is dark.",
}

GLOSSARY_VOICES = {
    "pillager": ["pirate", "riddle"],
}


def get_entity_glossary(entity: str):
    if entity in ENTITY_GLOSSARY:
        return ENTITY_GLOSSARY[entity]
    else:
        raise ValueError(f"Unknown entity {entity}")


def identifier_to_name(identifier: str):
    return identifier.lower().replace("_", " ")


class MinecraftEnvironment(Environment):
    def get_prompt(self, params: dict[str, str]) -> (str, list[str]):
        params = defaultdict(str, params)

        prompt = [system]

        # Entity description
        prompt.append(f"You are: {get_entity_glossary(params['entity'])}")

        # Environment description
        if "biome" in params:
            if params["biome"] in BIOME_GLOSSARY:
                prompt.append(BIOME_GLOSSARY[params["biome"]])
            else:
                prompt.append(
                    f"You are in a {identifier_to_name(params['biome'])} biome."
                )

        if "weather" in params and params["weather"] in WEATHER_GLOSSARY:
            prompt.append(WEATHER_GLOSSARY[params["weather"]])

        if "time" in params and params["time"] in TIME_GLOSSARY:
            prompt.append(TIME_GLOSSARY[params["time"]])

        if "light" in params and params["light"] in LIGHT_GLOSSARY:
            prompt.append(LIGHT_GLOSSARY[params["light"]])

        if "nearby" in params:
            prompt.append(params["nearby"])

        # Status description
        if "hand" in params:
            prompt.append(f"You are holding a {identifier_to_name(params['hand'])}.")

        # Status description
        if "offhand" in params:
            prompt.append(
                f"In your offhand you have a {identifier_to_name(params['offhand'])}."
            )

        if "armor" in params:
            prompt.append(f"You are wearing {identifier_to_name(params['armor'])}.")

        if "health" in params:
            prompt.append(HEALTH_GLOSSARY[params["health"]])

        # Target
        if "target_hand" in params:
            prompt.append(
                f"The target is holding a {identifier_to_name(params['target_weapon'])}."
            )

        if "target_offhand" in params:
            prompt.append(
                f"The target is holding a {identifier_to_name(params['target_weapon'])} in the offhand."
            )

        if "target_armor" in params:
            prompt.append(
                f"The target is wearing {identifier_to_name(params['target_armor'])}."
            )

        if "target_health" in params:
            prompt.append(TARGET_HEALTH_GLOSSARY[params["target_health"]])

        # Task description
        if params["task"] == "attack":
            prompt.append(
                f"You just spotted an enemy and prepare to attack: {get_entity_glossary(params['target'])}"
            )
        elif params["task"] == "defend":
            prompt.append(
                f"You got attacked by: {get_entity_glossary(params['target'])}"
            )
        elif params["task"] == "hurt":
            prompt.append(
                f"You just got punched by: {get_entity_glossary(params['target'])}"
            )
        elif params["task"] == "greet":
            prompt.append(
                f"You just met a friendly entity: {get_entity_glossary(params['target'])}"
            )
        elif params["task"] == "dialogue":
            if params["target"] == params["entity"]:
                prompt.append(
                    f"You just met another entity of your kind and have a conversation. You both share the same intention, goal, and personality."
                )
            else:
                prompt.append(
                    f"You just met a friendly entity you have a conversation with: {get_entity_glossary(params['target'])}"
                )
        elif params["task"] == "idle":
            prompt.append(f"You are wandering around, looking for something to do.")
        else:
            raise ValueError(f"Invalid task {params['task']}")

        return "\n".join(prompt)

    def get_filter(self, params: dict[str, str]) -> (str, list[str]):
        tags = ["task", "entity", "target"]

        return tags

    def simulate(self):
        possible = []
        for task in ["attack", "defend", "hurt", "greet", "dialogue", "idle"]:
            for entity in ENTITY_GLOSSARY:
                for target in [entity] if task == "dialogue" else ENTITY_GLOSSARY:
                    possible.append({"task": task, "entity": entity, "target": target})

    def get_valid_voices(self, params: dict[str, str]) -> list[str]:
        return (
            GLOSSARY_VOICES[params["entity"]]
            if params["entity"] in GLOSSARY_VOICES
            else ["pirate"]
        )

    def get_json_format(self, params: dict[str, str]) -> JsonFormat:
        if params["task"] == "dialogue":
            return JsonFormat.DIALOGUE
        else:
            return JsonFormat.PHRASES
