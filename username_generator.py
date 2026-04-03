"""
Username generator — 500 adjectives × 500 nouns × random suffix
Produces usernames like "ambitious-falcon42" or "vivid-reef817"
With suffixes, yields millions of unique combinations.
"""
import random
from models import User

ADJECTIVES = [
    'able', 'active', 'adept', 'agile', 'alert', 'alive', 'alpha', 'amber', 'ample', 'antic',
    'apt', 'aqua', 'arch', 'arid', 'artful', 'astral', 'astute', 'atomic', 'august', 'avid',
    'azure', 'balmy', 'basic', 'blazing', 'bliss', 'bold', 'bonny', 'brash', 'brave', 'bravo',
    'breezy', 'brief', 'bright', 'brisk', 'broad', 'bronze', 'burly', 'busy', 'calm', 'candid',
    'canny', 'cedar', 'chief', 'chill', 'civic', 'civil', 'clean', 'clear', 'clever', 'close',
    'cloud', 'cocky', 'cool', 'coral', 'core', 'cosy', 'cozy', 'craft', 'crisp', 'cubic',
    'curly', 'cute', 'cyber', 'daily', 'dapper', 'daring', 'deft', 'delta', 'dense', 'dewy',
    'dizzy', 'dormy', 'draft', 'dream', 'drift', 'dry', 'dual', 'dusk', 'dusty', 'eager',
    'early', 'earth', 'easy', 'ebony', 'edgy', 'eerie', 'eight', 'elfin', 'elite', 'ember',
    'empty', 'epic', 'equal', 'even', 'exact', 'extra', 'fable', 'faded', 'fair', 'fancy',
    'fast', 'fawn', 'feral', 'fiery', 'final', 'fine', 'firm', 'first', 'fixed', 'fizzy',
    'fleet', 'flint', 'fluid', 'flush', 'focal', 'foggy', 'fond', 'forge', 'forth', 'frank',
    'fresh', 'front', 'frost', 'frugal', 'full', 'funky', 'fuzzy', 'gamma', 'gaudy', 'gazer',
    'giddy', 'gilt', 'glad', 'gleam', 'glib', 'glint', 'glow', 'gold', 'gone', 'good',
    'grace', 'grand', 'grasp', 'grave', 'great', 'green', 'grey', 'grim', 'grit', 'gross',
    'grown', 'gusty', 'gutsy', 'hairy', 'hale', 'handy', 'happy', 'hardy', 'haste', 'haute',
    'hazel', 'heard', 'heart', 'heavy', 'heist', 'hex', 'hilly', 'honed', 'honor', 'hued',
    'husky', 'hyper', 'icy', 'ideal', 'inert', 'inner', 'ionic', 'iron', 'ivory', 'jade',
    'jazzy', 'jet', 'jewel', 'jolly', 'jovial', 'jumpy', 'juicy', 'just', 'karma', 'keen',
    'kind', 'known', 'kraft', 'laced', 'lanky', 'large', 'laser', 'late', 'latte', 'leafy',
    'lean', 'level', 'light', 'lilac', 'lithe', 'live', 'lofty', 'long', 'lost', 'loud',
    'loved', 'loyal', 'lucid', 'lucky', 'lunar', 'lush', 'lyric', 'macro', 'magic', 'major',
    'maple', 'matte', 'maven', 'meek', 'merry', 'metal', 'micro', 'mild', 'minty', 'misty',
    'mixed', 'modal', 'moist', 'moral', 'mossy', 'moved', 'muggy', 'mural', 'muted', 'mystic',
    'naive', 'named', 'nappy', 'natal', 'naval', 'near', 'neat', 'neon', 'nerve', 'new',
    'next', 'night', 'nimble', 'noble', 'north', 'noted', 'novel', 'oaken', 'oasis', 'ocean',
    'olive', 'omega', 'onset', 'opal', 'open', 'orbit', 'other', 'outer', 'oval', 'oxide',
    'paced', 'pale', 'palm', 'paper', 'pastel', 'peak', 'pearl', 'perky', 'petal', 'phlox',
    'pilot', 'pine', 'pixel', 'plaid', 'plain', 'plane', 'plank', 'plush', 'polar', 'polite',
    'pomp', 'posed', 'power', 'press', 'pride', 'prime', 'prior', 'prism', 'privy', 'proof',
    'proud', 'proxy', 'pulse', 'pure', 'push', 'quail', 'quasi', 'queen', 'query', 'quest',
    'quick', 'quiet', 'quirky', 'quota', 'radial', 'range', 'rapid', 'rare', 'raven', 'razer',
    'ready', 'rebel', 'regal', 'relay', 'retro', 'ridge', 'right', 'rigid', 'risen', 'risky',
    'rival', 'river', 'roast', 'rocky', 'rogue', 'roost', 'rosy', 'rough', 'round', 'rover',
    'royal', 'ruby', 'ruled', 'rural', 'rusty', 'sable', 'safe', 'sage', 'sandy', 'satin',
    'savor', 'scale', 'scrub', 'seven', 'shady', 'shall', 'sharp', 'sheer', 'shelf', 'shift',
    'shore', 'short', 'shown', 'sigma', 'silky', 'sixth', 'sleek', 'slick', 'slim', 'smart',
    'smoky', 'snowy', 'snug', 'solar', 'solid', 'sonic', 'south', 'space', 'spare', 'spicy',
    'spine', 'spire', 'spoke', 'stark', 'steam', 'steel', 'steep', 'stern', 'still', 'stoic',
    'stone', 'stony', 'storm', 'stout', 'straw', 'strip', 'stuck', 'suave', 'sunny', 'super',
    'sure', 'surge', 'swift', 'sworn', 'tacit', 'tango', 'tawny', 'tempo', 'tepid', 'terra',
    'terse', 'theta', 'thick', 'tidal', 'tidy', 'tiger', 'tight', 'timid', 'titan', 'toast',
    'token', 'topaz', 'torch', 'total', 'tough', 'tower', 'trace', 'trail', 'tread', 'treat',
    'trend', 'triad', 'trick', 'tried', 'trine', 'trope', 'trout', 'truly', 'trump', 'trust',
    'tuned', 'turbo', 'tween', 'tweed', 'twin', 'typed', 'ultra', 'umbra', 'under', 'union',
    'unity', 'upper', 'urban', 'usual', 'utter', 'valid', 'valor', 'vapor', 'vault', 'velvet',
    'verse', 'vivid', 'vocal', 'vogue', 'voila', 'volt', 'vowed', 'wager', 'warm', 'waved',
    'weary', 'wheat', 'whole', 'wider', 'wild', 'windy', 'wired', 'wise', 'witty', 'woken',
    'woody', 'worth', 'xenon', 'yacht', 'yawny', 'young', 'zappy', 'zebra', 'zendo', 'zephyr',
    'zesty', 'zippy', 'zonal', 'zoom',
]

NOUNS = [
    'ace', 'acre', 'aero', 'ally', 'alps', 'alto', 'amp', 'anchor', 'angel', 'apex',
    'arch', 'arrow', 'ash', 'atlas', 'atom', 'aura', 'axis', 'badge', 'bank', 'bark',
    'barn', 'baron', 'base', 'basin', 'bay', 'beach', 'beam', 'bear', 'beast', 'bell',
    'bend', 'berry', 'birch', 'bird', 'blade', 'blaze', 'blend', 'bliss', 'block', 'bloom',
    'bluff', 'board', 'bolt', 'bone', 'bonus', 'boost', 'boots', 'boss', 'bow', 'brace',
    'brain', 'brand', 'brass', 'brave', 'brick', 'brook', 'brush', 'buck', 'buddy', 'build',
    'bull', 'burst', 'cabin', 'cache', 'cairn', 'camp', 'candy', 'cape', 'cargo', 'cedar',
    'chain', 'chalk', 'champ', 'charm', 'chase', 'chess', 'chief', 'chip', 'chord', 'claim',
    'clash', 'claw', 'cliff', 'climb', 'clock', 'cloud', 'clue', 'coast', 'coil', 'comet',
    'conch', 'cone', 'coral', 'core', 'couch', 'court', 'cover', 'crane', 'crash', 'crate',
    'creek', 'crest', 'crew', 'cross', 'crown', 'crush', 'crust', 'crypt', 'cube', 'curve',
    'cycle', 'dagger', 'daisy', 'dance', 'dawn', 'deal', 'deck', 'delta', 'den', 'depot',
    'derby', 'desk', 'dew', 'dial', 'dice', 'dime', 'dingo', 'disc', 'dock', 'dodge',
    'dome', 'dose', 'dove', 'draft', 'drain', 'drake', 'dream', 'drift', 'drill', 'drive',
    'drone', 'drum', 'duke', 'dune', 'dusk', 'eagle', 'earth', 'echo', 'edge', 'eight',
    'elk', 'elm', 'ember', 'ensign', 'entry', 'envoy', 'epoch', 'eve', 'event', 'exile',
    'fable', 'face', 'faith', 'falcon', 'fame', 'fang', 'farm', 'fawn', 'feast', 'ferry',
    'fiber', 'field', 'finch', 'fire', 'fjord', 'flag', 'flame', 'flare', 'flash', 'fleet',
    'flint', 'flock', 'flood', 'floor', 'flora', 'flute', 'flux', 'foam', 'focus', 'forge',
    'fork', 'form', 'fort', 'forum', 'fossil', 'fox', 'frame', 'frost', 'fruit', 'fuel',
    'fury', 'fuse', 'gain', 'gale', 'game', 'gate', 'gauge', 'gear', 'gem', 'ghost',
    'giant', 'gift', 'glade', 'glare', 'glass', 'gleam', 'glen', 'globe', 'glory', 'glow',
    'gold', 'gorge', 'grace', 'grain', 'grant', 'grape', 'grasp', 'grass', 'grave', 'grip',
    'grove', 'growl', 'guard', 'guest', 'guide', 'guild', 'gulch', 'gull', 'guru', 'gust',
    'habit', 'hail', 'halo', 'haven', 'hawk', 'hazel', 'heart', 'hedge', 'heist', 'helm',
    'hero', 'heron', 'hiker', 'hinge', 'holly', 'honor', 'hood', 'hook', 'horn', 'horse',
    'host', 'house', 'hulk', 'husk', 'hydra', 'ibis', 'icon', 'igloo', 'imp', 'index',
    'inlet', 'iron', 'isle', 'ivory', 'ivy', 'jack', 'jade', 'jay', 'jewel', 'joker',
    'judge', 'juice', 'jumbo', 'kayak', 'keep', 'ketch', 'key', 'king', 'kite', 'knack',
    'knave', 'kneel', 'knife', 'knob', 'knoll', 'knot', 'koala', 'kraft', 'kudos', 'lake',
    'lance', 'lane', 'larch', 'lark', 'laser', 'latch', 'lathe', 'lawn', 'leaf', 'ledge',
    'lever', 'light', 'lilac', 'lime', 'linen', 'link', 'lion', 'llama', 'locus', 'lodge',
    'loft', 'logic', 'lotus', 'lunar', 'lunge', 'lynx', 'mace', 'magic', 'manor', 'maple',
    'march', 'mare', 'marsh', 'mason', 'mast', 'match', 'maze', 'medal', 'mesa', 'metro',
    'might', 'mill', 'mine', 'mint', 'moat', 'model', 'molar', 'monk', 'moon', 'moor',
    'moose', 'moss', 'motor', 'mound', 'mouse', 'mural', 'myth', 'nebula', 'nerve', 'nest',
    'nexus', 'night', 'noble', 'node', 'north', 'notch', 'nova', 'oak', 'oar', 'oasis',
    'ocean', 'olive', 'omega', 'onyx', 'orbit', 'orca', 'order', 'ore', 'osprey', 'otter',
    'owl', 'oxide', 'ozone', 'pace', 'pack', 'panda', 'panel', 'park', 'path', 'patio',
    'pawn', 'peak', 'pearl', 'petal', 'phase', 'pier', 'pike', 'pilot', 'pine', 'pixel',
    'plain', 'plane', 'plank', 'plant', 'plaza', 'plume', 'pluto', 'point', 'polar', 'pond',
    'poppy', 'port', 'posse', 'pouch', 'power', 'press', 'pride', 'prism', 'prize', 'probe',
    'proxy', 'prune', 'pulse', 'puma', 'quail', 'quake', 'quark', 'queen', 'quest', 'quota',
    'radar', 'raft', 'raid', 'rally', 'ranch', 'range', 'rapid', 'raven', 'razer', 'reach',
    'realm', 'rebel', 'reef', 'reign', 'relay', 'relic', 'ridge', 'rifle', 'ring', 'river',
    'roam', 'robin', 'rock', 'rod', 'rogue', 'roof', 'root', 'rope', 'route', 'rover',
    'ruby', 'rust', 'sage', 'sail', 'salon', 'sand', 'satin', 'savor', 'scale', 'scout',
    'seal', 'seed', 'shard', 'shark', 'shelf', 'shell', 'shift', 'shore', 'shrub', 'siege',
    'sigma', 'slate', 'slope', 'smith', 'smoke', 'snare', 'solar', 'sonic', 'south', 'spark',
    'spear', 'spice', 'spine', 'spire', 'spoke', 'spore', 'spray', 'squad', 'staff', 'stage',
    'stake', 'star', 'steam', 'steel', 'steed', 'stern', 'stock', 'stone', 'stork', 'storm',
    'stove', 'straw', 'stump', 'surge', 'swan', 'sweep', 'swift', 'sword', 'table', 'talon',
    'tango', 'tempo', 'terra', 'theta', 'thorn', 'thyme', 'tide', 'tiger', 'titan', 'toast',
    'token', 'topaz', 'torch', 'tower', 'trace', 'track', 'trail', 'trait', 'tramp', 'triad',
    'tribe', 'trick', 'troop', 'trout', 'truce', 'trunk', 'trust', 'tulip', 'tuner', 'tunic',
    'tusks', 'twig', 'twist', 'ultra', 'unity', 'upper', 'valve', 'vapor', 'vault', 'verse',
    'vigor', 'vine', 'viola', 'viper', 'vista', 'voice', 'volta', 'vortex', 'voter', 'wager',
    'wagon', 'watch', 'water', 'wave', 'wheat', 'wheel', 'whirl', 'whole', 'width', 'wilds',
    'wind', 'wing', 'wire', 'witch', 'wizard', 'wolf', 'wonder', 'world', 'wrath', 'wren',
    'yacht', 'yarn', 'yeti', 'yield', 'yoke', 'zebra', 'zenith', 'zephyr', 'zero', 'zone',
]


def generate_unique_username(max_attempts=20):
    """
    Generate a unique username: adjective-noun + random 2-4 digit suffix.
    500 × 500 × ~9000 suffixes = ~2.25 billion possible combinations.
    Falls back to timestamp-based username after max_attempts.
    """
    import time
    for _ in range(max_attempts):
        adj = random.choice(ADJECTIVES)
        noun = random.choice(NOUNS)
        suffix = random.randint(10, 9999)
        username = f"{adj}-{noun}{suffix}"
        try:
            if not User.query.filter_by(username=username).first():
                return username
        except Exception:
            break
    # Fallback — virtually impossible to collide
    return f"user-{int(time.time())}{random.randint(100, 999)}"
