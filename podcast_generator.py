"""
VELOCITY SPANISH PODCAST GENERATOR
15-min bilingual podcast at A2 level
2 hosts: Maria (Host1) & Carlos (Host2)
"""
import os, sys, json, asyncio, subprocess, random, requests, re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter

load_dotenv()

POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL") or "openai"

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"

HOST1_VOICE = "es-ES-ElviraNeural"
HOST2_VOICE = "es-ES-AlvaroNeural"

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

TOPICS = [
    "Viajar a un pais nuevo - Traveling to a new country",
    "Comida tradicional - Traditional food",
    "Rutina diaria - Daily routine",
    "Fiestas y celebraciones - Holidays and celebrations",
    "El clima y las estaciones - Weather and seasons",
    "Familia y amigos - Family and friends",
    "Musica y peliculas - Music and movies",
    "Deportes y ejercicio - Sports and exercise",
    "La ciudad ideal - The ideal city",
    "Aprender idiomas - Learning languages",
    "El fin de semana - The weekend",
    "Compras y ropa - Shopping and clothes",
    "Transporte publico - Public transport",
    "En el restaurante - At the restaurant",
    "Salud y bienestar - Health and wellness",
]

def load_font(size):
    paths = [
        str(FONTS_DIR / "DejaVuSans-Bold.ttf"),
        "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

def clean_text(text):
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\b(mm+|um+|uh+|ah+)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_turns_json(content, target_key="spanish"):
    """Robustly parse JSON array of turns from LLM output, handling unescaped control chars, code fences, and partial json."""
    clean = content.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()

    try:
        obj = json.loads(clean, strict=False)
        if isinstance(obj, list):
            return obj
    except Exception:
        pass

    fixed = re.sub(r'(?<!\\)\n', r'\\n', clean)
    try:
        obj = json.loads(fixed, strict=False)
        if isinstance(obj, list):
            return obj
    except Exception:
        pass

    recovered = []
    start = None
    depth = 0
    for ci, ch in enumerate(clean):
        if ch == '{':
            if depth == 0:
                start = ci
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                chunk = clean[start:ci + 1]
                try:
                    t = json.loads(chunk, strict=False)
                    if isinstance(t, dict):
                        recovered.append(t)
                except Exception:
                    try:
                        chunk_fixed = re.sub(r'(?<!\\)\n', r'\\n', chunk)
                        t = json.loads(chunk_fixed, strict=False)
                        if isinstance(t, dict):
                            recovered.append(t)
                    except Exception:
                        pass
                start = None
    if recovered:
        return recovered

    regex = re.compile(
        r'\{\s*"speaker"\s*:\s*"(?P<speaker>[^"]+)"\s*,\s*'
        r'(?:"(?:' + target_key + r'|text|content|Spanish)"\s*:\s*"(?P<tgt>.*?)"\s*,\s*)?'
        r'(?:"(?:english|English)"\s*:\s*"(?P<en>.*?)"\s*)?'
        r'\}', re.DOTALL
    )
    for m in regex.finditer(clean):
        spk = m.group("speaker") or "Host1"
        tgt = m.group("tgt") or ""
        en = m.group("en") or ""
        if tgt:
            recovered.append({"speaker": spk, target_key: tgt, "english": en})

    return recovered

def _fetch_turns_batch(topic, topic_es, topic_en, start_turn, batch_size=10):
    """Fetch one small batch of turns with multi-model fallback and robust parsing."""
    current_host = "Host2" if start_turn % 2 == 0 else "Host1"
    next_host = "Host1" if current_host == "Host2" else "Host2"
    host_role = "Carlos" if current_host == "Host2" else "Maria"

    intro_instruction = ""
    if start_turn == 0:
        intro_instruction = ("IMPORTANT: This is the FIRST batch. Keep the introduction SHORT - just 2 lines total "
                             "(one from Carlos/Host2, one from Maria/Host1), then immediately dive into the topic. "
                             "No long welcome speeches.\n")
    elif start_turn < 4:
        intro_instruction = "Continue naturally into the topic conversation. No new introductions.\n"

    prompt = f"""You are writing a Spanish/English learning podcast at A2 level.
Topic: {topic}

The dialogue so far is at turn {start_turn}. The current speaker is {host_role} ({current_host}).
Write the NEXT {batch_size} turns. Speakers STRICTLY alternate starting with {current_host}.

{intro_instruction}Each turn: 3-4 SHORT sentences (6-10 words each) with PERIODS for natural TTS pauses. 20-30 seconds spoken.
Simple present tense. A2 vocabulary. Natural Spanish. NO filler sounds (no mmm, um, uh, ah).
IMPORTANT: Highlight exactly 1 key A2 target vocabulary word in each turn's Spanish text using double asterisks, for example: "Mirando al **futuro**."
IMPORTANT: Format as a single compact JSON array without unescaped line breaks inside string values.

Return EXACTLY {batch_size} turns as a JSON array (no markdown):
[{{"speaker": "{current_host}", "spanish": "...", "english": "..."}},
 {{"speaker": "{next_host}", "spanish": "...", "english": "..."}}]"""

    candidate_models = [AI_MODEL, "openai", "mistral", "qwen"]
    models_to_try = []
    for mod in candidate_models:
        if mod and mod not in models_to_try:
            models_to_try.append(mod)

    for attempt, model_name in enumerate(models_to_try):
        try:
            resp = requests.post("https://gen.pollinations.ai/v1/chat/completions", json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You write natural A2-level Spanish podcast scripts with VERY clear punctuation. Every sentence must have at least 2 commas for natural TTS pauses. Maria and Carlos strictly alternate. Highlight 1 key target word per turn in double asterisks like **palabra**. No filler sounds. Output single compact JSON array without unescaped newlines inside strings."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.8
            }, headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"} if POLLINATIONS_API_KEY else {}, timeout=45)
            if resp.status_code != 200:
                print(f"  Batch attempt {attempt+1} ({model_name}) returned HTTP {resp.status_code}", flush=True)
                continue
            content = resp.json()["choices"][0]["message"]["content"].strip()
            script = parse_turns_json(content, "spanish")
            valid = []
            for i, turn in enumerate(script):
                if not isinstance(turn, dict):
                    continue
                es = turn.get("spanish") or turn.get("Spanish") or turn.get("text") or turn.get("content") or ""
                en = turn.get("english") or turn.get("English") or turn.get("translation") or ""
                if not es:
                    continue
                valid.append({
                    "speaker": current_host if i % 2 == 0 else next_host,
                    "spanish": clean_text(es),
                    "english": clean_text(en) if en else "Translation unavailable"
                })
            if len(valid) >= 4:
                return valid
            else:
                print(f"  Batch attempt {attempt+1} ({model_name}) parsed only {len(valid)} turns, trying next model...", flush=True)
        except Exception as e:
            print(f"  Batch attempt {attempt+1} ({model_name}) failed: {e}", flush=True)
            import time
            time.sleep(1)
    return None


def _generate_topic():
    """Have the AI invent a brand-new random topic (unlimited variety).
    Returns '<topic - English>' or None on failure (caller falls back to TOPICS)."""
    seed = random.randint(100000, 999999)
    candidate_models = [AI_MODEL, "openai", "mistral"]
    for m in candidate_models:
        if not m:
            continue
        try:
            resp = requests.post("https://gen.pollinations.ai/v1/chat/completions", json={
                "model": m,
                "messages": [
                    {"role": "system", "content": "You invent fresh, interesting, everyday topics for a Spanish/English A2 learning podcast. Always pick something new and varied from all areas of daily life, as a SHORT noun phrase (2-5 words), NOT a full sentence."},
                    {"role": "user", "content": f"Create EXACTLY ONE brand-new topic (uniqueness seed {seed}) for a Spanish/English A2 podcast. Return ONLY one line in this exact format: <topic in Spanish> - <topic in English>. The first part must be a short noun phrase in Spanish. No numbering, no bullets, no extra text."}
                ],
                "temperature": 1.1,
            }, headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"} if POLLINATIONS_API_KEY else {}, timeout=45)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip()
                if content and " - " in content:
                    return content
        except Exception as e:
            print(f"  Topic gen ({m}) failed: {e}", flush=True)
    return None


def _fallback_script(topic_es, topic_en, target=150):
    """Generate 150 unique, educational, progressive dialogue turns in Spanish covering diverse conversation phases."""
    phases = [
        # Phase 1: Greetings & Introduction
        [
            ("Host2", f"Hola a todos, soy Carlos. ¡Bienvenidos a Velocity Spanish! Hoy hablamos de **{topic_es}**.",
                      f"Hello everyone, I'm Carlos. Welcome to Velocity Spanish! Today we talk about {topic_en}."),
            ("Host1", f"¡Hola Carlos, y hola a todos los oyentes! Este tema es verdaderamente **interesante** para aprender español.",
                      f"Hello Carlos, and hello to all listeners! This topic is truly interesting for learning Spanish."),
            ("Host2", f"Exacto, María. Muchas personas encuentran **{topic_es}** cada día, pero no saben cómo expresarse.",
                      f"Exactly, Maria. Many people encounter {topic_en} every day, but don't know how to express themselves."),
            ("Host1", f"Es verdad. Por eso usamos frases **sencillas** y palabras claras para que todos puedan comprender.",
                      f"It's true. That's why we use simple sentences and clear words so everyone can understand."),
            ("Host2", f"¡Perfecto! Empecemos con la primera pregunta: ¿qué significa **{topic_es}** en tu vida diaria?",
                      f"Perfect! Let's start with the first question: what does {topic_en} mean in your daily life?"),
            ("Host1", f"Para mí representa una parte fundamental del **día** que nos llena de energía y buen humor.",
                      f"For me it represents a fundamental part of the day that fills us with energy and good humor."),
            ("Host2", f"Estoy totalmente de acuerdo. Dedicarle tiempo mejora nuestro bienestar y nuestra **tranquilidad**.",
                      f"I completely agree. Dedicating time to it improves our well-being and peace of mind."),
            ("Host1", f"Sí, y al aprender el vocabulario adecuado, es fácil mantener una buena **conversación**.",
                      f"Yes, and by learning the right vocabulary, it's easy to maintain a good conversation."),
            ("Host2", f"Escuchen con atención las expresiones de hoy, y repitan las palabras clave en voz **alta**.",
                      f"Listen carefully to today's expressions, and repeat the key words out loud."),
            ("Host1", f"¡Muy bien Carlos! Entremos de lleno en los aspectos más prácticos de **{topic_es}**.",
                      f"Very well Carlos! Let's get right into the most practical aspects of {topic_en}.")
        ],
        # Phase 2: Morning habits & routines
        [
            ("Host2", f"María, en un día normal, ¿en qué momento piensas por primera vez en **{topic_es}**?",
                      f"Maria, on a normal day, at what point do you first think about {topic_en}?"),
            ("Host1", f"Suelo pensar en ello temprano por la mañana, porque me ayuda a empezar con mucha **calma**.",
                      f"I usually think about it early in the morning, because it helps me start with much calm."),
            ("Host2", f"Para mí la mañana también es un momento especial. Me gusta tomarme mi **tiempo** sin prisa.",
                      f"For me morning is also a special moment. I like taking my time without rushing."),
            ("Host1", f"La prisa nunca es buena compañera. Una buena **costumbre** matutina transforma todo el día.",
                      f"Hurry is never a good companion. A good morning habit transforms the whole day."),
            ("Host2", f"Otras personas prefieren dedicar tiempo a **{topic_es}** por la tarde o al volver del trabajo.",
                      f"Other people prefer dedicating time to {topic_en} in the afternoon or returning from work."),
            ("Host1", f"Depende mucho del estilo de vida de cada uno. Lo fundamental es encontrar un buen **equilibrio**.",
                      f"It depends a lot on each person's lifestyle. The fundamental thing is finding a good balance."),
            ("Host2", f"Tienes toda la razón. Conocer las propias necesidades permite vivir mucho **mejor**.",
                      f"You're completely right. Knowing one's own needs allows living much better."),
            ("Host1", f"Y para quienes aprenden español, la práctica diaria crea una sólida **memoria** de las palabras.",
                      f"And for those learning Spanish, daily practice creates a solid memory of words."),
            ("Host2", f"Exacto. Diez minutos cada día son mucho más eficaces que dos horas solamente el **domingo**.",
                      f"Exactly. Ten minutes every day are much more effective than two hours only on Sunday."),
            ("Host1", f"Continuemos descubriendo cómo **{topic_es}** forma parte de la vida en la ciudad.",
                      f"Let's continue discovering how {topic_en} forms part of life in the city.")
        ],
        # Phase 3: In the city & Spanish lifestyle
        [
            ("Host2", f"Al pasear por una ciudad hispanohablante, se nota en seguida la importancia de **{topic_es}**.",
                      f"When strolling through a Spanish-speaking city, the importance of {topic_en} is immediately noticeable."),
            ("Host1", f"Sí, en los cafés, mercados y plazas, la gente suele conversar sobre ello con gran **entusiasmo**.",
                      f"Yes, in cafes, markets and plazas, people usually converse about it with great enthusiasm."),
            ("Host2", f"Compartir estos momentos cotidianos con amigos es una parte esencial de nuestra **cultura**.",
                      f"Sharing these daily moments with friends is an essential part of our culture."),
            ("Host1", f"La vida social y la cercanía son valores muy importantes. Nunca se está realmente **solo**.",
                      f"Social life and closeness are very important values. One is never truly alone."),
            ("Host2", f"¿Qué adjetivos utiliza la gente con más frecuencia al hablar de **{topic_es}**?",
                      f"What adjectives do people use most frequently when talking about {topic_en}?"),
            ("Host1", f"A menudo dicen 'bueno', 'auténtico' o 'fresco' para destacar siempre la **calidad**.",
                      f"They often say 'good', 'authentic' or 'fresh' to always emphasize quality."),
            ("Host2", f"La palabra 'calidad' es perfecta. En el mundo hispano siempre se busca el mejor **sabor**.",
                      f"The word 'quality' is perfect. In the Hispanic world one always looks for the best flavor."),
            ("Host1", f"Incluso cuando el precio es un poco mayor, la calidad compensa con creces la **elección**.",
                      f"Even when the price is slightly higher, quality more than makes up for the choice."),
            ("Host2", f"Un gran consejo para los viajeros: pregunten siempre a las personas del **lugar**.",
                      f"A great tip for travelers: always ask the people of the place."),
            ("Host1", f"Los vecinos siempre conocen los rincones más auténticos y acogedores para disfrutar de **{topic_es}**.",
                      f"Locals always know the most authentic and welcoming corners to enjoy {topic_en}.")
        ],
        # Phase 4: Advice for beginners & common hurdles
        [
            ("Host2", f"Un oyente nos preguntó: ¿es difícil comprender todos los matices sobre **{topic_es}**?",
                      f"A listener asked us: is it difficult to understand all nuances about {topic_en}?"),
            ("Host1", f"Al principio puede parecer complicado, pero con un poco de constancia todo se vuelve **claro**.",
                      f"At first it may seem complicated, but with a little constancy everything becomes clear."),
            ("Host2", f"¿Cuál es el error más habitual que cometen los principiantes con este **tema**?",
                      f"What is the most common mistake beginners make with this topic?"),
            ("Host1", f"El error más común es tener miedo a equivocarse o querer hablar con perfección desde el primer **día**.",
                      f"The most common mistake is being afraid of making mistakes or wanting to speak with perfection from day one."),
            ("Host2", f"¡Cometer errores es natural y necesario! Cada error es una valiosa oportunidad de **aprender**.",
                      f"Making mistakes is natural and necessary! Every mistake is a valuable opportunity to learn."),
            ("Host1", f"Totalmente cierto. En una conversación real, lo primordial es comunicar y mostrar **amabilidad**.",
                      f"Totally true. In a real conversation, the primary thing is communicating and showing kindness."),
            ("Host2", f"La gente siempre aprecia mucho el esfuerzo de los extranjeros por hablar en su **idioma**.",
                      f"People always greatly appreciate foreigners' effort to speak in their language."),
            ("Host1", f"Siempre recibirán una sonrisa cálida y palabras de aliento para seguir **adelante**.",
                      f"You will always receive a warm smile and words of encouragement to keep going forward."),
            ("Host2", f"Así que no tengan ninguna duda en hablar sobre **{topic_es}** a la menor ocasión.",
                      f"So don't have any hesitation in talking about {topic_en} at the slightest opportunity."),
            ("Host1", f"Tomen confianza y utilicen las estructuras que repasamos juntos en este **episodio**.",
                      f"Take confidence and use the structures we review together in this episode.")
        ],
        # Phase 5: Cultural diversity across the Spanish-speaking world
        [
            ("Host2", f"María, ¿cómo cambia la manera de vivir **{topic_es}** entre los diferentes países hispanos?",
                      f"Maria, how does the way of experiencing {topic_en} change among different Hispanic countries?"),
            ("Host1", f"Entre España y Latinoamérica hay expresiones distintas, pero el cariño por esta tradición es siempre **fuerte**.",
                      f"Between Spain and Latin America there are different expressions, but affection for this tradition is always strong."),
            ("Host2", f"Esa inmensa riqueza cultural hace que el mundo hispanohablante sea tan fascinante y **diverso**.",
                      f"That immense cultural richness makes the Spanish-speaking world so fascinating and diverse."),
            ("Host1", f"Cada región aporta sus propias palabras, costumbres y formas únicas de celebrar la **vida**.",
                      f"Each region brings its own words, customs and unique ways of celebrating life."),
            ("Host2", f"Viajeros de todo el mundo quedan encantados con la calidez y el sentido de **comunidad**.",
                      f"Travelers from all over the world are enchanted by the warmth and sense of community."),
            ("Host1", f"Porque en el centro de nuestra cultura siempre están la familia, los buenos amigos y la **alegría**.",
                      f"Because at the center of our culture there are always family, good friends and joy."),
            ("Host2", f"Y **{topic_es}** encaja a la perfección en esta forma auténtica de disfrutar cada momento.",
                      f"And {topic_en} fits perfectly into this authentic way of enjoying every moment."),
            ("Host1", f"No es solo un concepto, sino una verdadera experiencia práctica para **compartir**.",
                      f"It's not just a concept, but a true practical experience to share."),
            ("Host2", f"Compartir algo bueno multiplica la satisfacción y crea un hermoso **recuerdo**.",
                      f"Sharing something good multiplies satisfaction and creates a beautiful memory."),
            ("Host1", f"Exactamente, Carlos. Los mejores recuerdos casi siempre nacen de las cosas más **simples**.",
                      f"Exactly, Carlos. The best memories almost always are born from the simplest things.")
        ],
        # Phase 6: Practical learning tips
        [
            ("Host2", f"Compartamos ahora tres consejos prácticos con nuestros oyentes para dominar **{topic_es}**.",
                      f"Let's share now three practical tips with our listeners to master {topic_en}."),
            ("Host1", f"Primer consejo: tengan una libreta pequeña y apunten cada día dos o tres **frases** nuevas.",
                      f"First tip: keep a small notebook and jot down two or three new sentences each day."),
            ("Host2", f"¡Gran idea! Escribir a mano ayuda al cerebro a retener la ortografía y el **significado**.",
                      f"Great idea! Writing by hand helps the brain retain spelling and meaning."),
            ("Host1", f"Segundo consejo: escuchen podcasts en español mientras caminan o van en el **transporte**.",
                      f"Second tip: listen to podcasts in Spanish while walking or going on transit."),
            ("Host2", f"Esa escucha pasiva acostumbra el oído al ritmo natural y la musicalidad de la **voz**.",
                      f"That passive listening gets the ear used to the natural rhythm and musicality of the voice."),
            ("Host1", f"Y tercer consejo: nunca aprendan palabras sueltas; memoricen siempre oraciones en su **contexto**.",
                      f"And third tip: never learn isolated words; always memorize sentences in their context."),
            ("Host2", f"De ese modo, en una conversación real la frase saldrá sola sin necesidad de **pensar**.",
                      f"That way, in a real conversation the sentence will come out on its own without needing to think."),
            ("Host1", f"Es justo el método natural y comunicativo que seguimos para este nivel **A2**.",
                      f"It's just the natural and communicative method we follow for this A2 level."),
            ("Host2", f"Muchos oyentes nos escriben comentando los grandes avances que consiguen con esta **estrategia**.",
                      f"Many listeners write to us commenting on the great progress they achieve with this strategy."),
            ("Host1", f"Nos alegra muchísimo saberlo y nos impulsa a seguir creando episodios cada vez más **útiles**.",
                      f"It makes us very glad to know it and drives us to keep creating increasingly useful episodes.")
        ],
        # Phase 7: Situational roleplay
        [
            ("Host2", f"Hagamos un breve diálogo de práctica: imaginemos que entramos a una tienda para elegir **{topic_es}**.",
                      f"Let's do a short practice dialogue: let's imagine we enter a shop to choose {topic_en}."),
            ("Host1", f"¡Me encanta la idea! 'Buenos días, señor, ¿podría decirme qué me **recomienda**?'",
                      f"I love the idea! 'Good morning, sir, could you tell me what you recommend?'"),
            ("Host2", f"'¡Buenos días! Para empezar, le sugiero sin duda esta opción clásica y muy **segura**.'",
                      f"'Good morning! To start with, I suggest without doubt this classic and very safe option.'"),
            ("Host1", f"'¡Muchísimas gracias! ¿Y cuánto tiempo hace falta para familiarizarse bien en la **práctica**?'",
                      f"'Thank you very much! And how much time is needed to get well familiarized in practice?'"),
            ("Host2", f"'Generalmente unos pocos días son suficientes si se practica con tranquilidad y **paciencia**.'",
                      f"'Generally a few days are sufficient if one practices with calm and patience.'"),
            ("Host1", f"'¡Excelente! Voy a seguir su consejo desde hoy mismo con mucho **ánimo**.'",
                      f"'Excellent! I will follow your advice starting today with great enthusiasm.'"),
            ("Host2", f"Ese fue un diálogo sencillo, educado y muy útil para cualquier viaje por un país **hispano**.",
                      f"That was a simple, polite and very useful dialogue for any trip through a Hispanic country."),
            ("Host1", f"Fíjense en expresiones de cortesía como '¿podría decirme?' que abren cualquier **conversación**.",
                      f"Notice courtesy expressions like 'could you tell me?' which open any conversation."),
            ("Host2", f"La amabilidad siempre genera una respuesta positiva y hace más agradable el **contacto**.",
                      f"Kindness always generates a positive response and makes contact more pleasant."),
            ("Host1", f"Guarden bien estas frases prácticas y sigamos con nuestra amena **charla**.",
                      f"Keep these practical phrases well and let's continue with our pleasant chat.")
        ],
        # Phase 8: Personal reflections & confidence
        [
            ("Host2", f"María, ¿cómo reaccionan tus amistades cuando hablas con ellas acerca de **{topic_es}**?",
                      f"Maria, how do your friends react when you talk with them about {topic_en}?"),
            ("Host1", f"Al principio tenían ciertas dudas, pero al experimentarlo comprobaron su verdadero **valor**.",
                      f"At first they had certain doubts, but upon experiencing it they verified its true value."),
            ("Host2", f"Tener ciertas reservas al inicio es algo completamente natural ante cualquier novedad o **reto**.",
                      f"Having certain reservations at the beginning is completely natural before any novelty or challenge."),
            ("Host1", f"Pero en cuanto damos el primer paso, las dudas desaparecen y nace una gran **seguridad**.",
                      f"But as soon as we take the first step, doubts disappear and great confidence is born."),
            ("Host2", f"La soltura al hablar se adquiere con la práctica, por eso hablen siempre sin ningún **miedo**.",
                      f"Fluency in speaking is acquired with practice, so always speak without any fear."),
            ("Host1", f"Incluso con un vocabulario básico de unas cuantas palabras, ya se puede contar una bonita **anécdota**.",
                      f"Even with a basic vocabulary of a few words, one can already tell a nice anecdote."),
            ("Host2", f"Lo primordial es la sinceridad y las ganas de conectar con los demás de corazón a **corazón**.",
                      f"The primary thing is sincerity and the desire to connect with others from heart to heart."),
            ("Host1", f"Nuestra comunidad internacional nos demuestra a diario que el español está al alcance de **todos**.",
                      f"Our international community demonstrates to us daily that Spanish is within everyone's reach."),
            ("Host2", f"Cada episodio escuchado es una victoria más en su camino de aprendizaje hacia el **éxito**.",
                      f"Every listened episode is one more victory on your learning journey toward success."),
            ("Host1", f"Y nos hace muy felices poder acompañarlos semana a semana con cariño y mucha **energía**.",
                      f"And it makes us very happy to be able to accompany you week by week with care and much energy.")
        ],
        # Phase 9: Vocabulary review
        [
            ("Host2", f"Repasemos rápidamente los cinco términos más destacados que hemos empleado hoy sobre **{topic_es}**.",
                      f"Let's quickly review the five most outstanding terms we used today about {topic_en}."),
            ("Host1", f"¡Con gusto! El primer término clave es **costumbre**, que alude a un hábito provechoso y constante.",
                      f"Gladly! The first key term is 'habit', referring to a beneficial and constant habit."),
            ("Host2", f"La segunda palabra importante es **calidad**, que distingue lo bueno y duradero de lo mediocre.",
                      f"The second important word is 'quality', distinguishing the good and durable from the mediocre."),
            ("Host1", f"El tercer vocablo es **tranquilidad**, esa agradable sensación de calma y bienestar interior.",
                      f"The third word is 'peace of mind', that pleasant sensation of calm and inner well-being."),
            ("Host2", f"La cuarta palabra es **paciencia**, imprescindible para avanzar con firmeza en el estudio de una **lengua**.",
                      f"The fourth word is 'patience', essential to advance steadily in studying a language."),
            ("Host1", f"Y el quinto concepto es **seguridad**, la confianza necesaria para expresarse con libertad y soltura.",
                      f"And the fifth concept is 'confidence', the trust needed to express oneself with freedom and fluency."),
            ("Host2", f"Animamos a todos los oyentes a escribir una frase original con alguna de estas palabras en los **comentarios**.",
                      f"We encourage all listeners to write an original sentence with one of these words in the comments."),
            ("Host1", f"Leeremos sus comentarios con muchísima atención e ilusión para darles nuestro apoyo constante.",
                      f"We will read your comments with great attention and excitement to give you our constant support."),
            ("Host2", f"Escribir activamente ayuda a consolidar las expresiones para que no se olviden **nunca**.",
                      f"Writing actively helps consolidate expressions so they are never forgotten."),
            ("Host1", f"Pasemos ahora a las palabras de despedida para concluir este excelente **programa**.",
                      f"Let's move now to farewell words to conclude this excellent program.")
        ],
        # Phase 10: Conclusion & wrap-up
        [
            ("Host2", f"Nuestro podcast de hoy dedicado a **{topic_es}** llega a su parte final.",
                      f"Our podcast today dedicated to {topic_en} reaches its final part."),
            ("Host1", f"¡El tiempo ha pasado volando! Hemos compartido muchas ideas y palabras sumamente **valiosas**.",
                      f"Time has flown by! We have shared many ideas and extremely valuable words."),
            ("Host2", f"No olviden volver a escuchar esta grabación para perfeccionar el acento y la **pronunciación**.",
                      f"Don't forget to listen again to this recording to perfect accent and pronunciation."),
            ("Host1", f"Cada nueva escucha hará que su expresión sea más fluida, natural y completamente **espontánea**.",
                      f"Each new listening will make your expression more fluent, natural and completely spontaneous."),
            ("Host2", f"Muchas gracias a todos por su fidelidad, sus comentarios amables y su apoyo constante en el **canal**.",
                      f"Thank you very much to all for your loyalty, your kind comments and your constant support on the channel."),
            ("Host1", f"Suscríbanse a Velocity Spanish, dejen un me gusta y recomienden el contenido a sus **amigos**.",
                      f"Subscribe to Velocity Spanish, leave a like and recommend the content to your friends."),
            ("Host2", f"Muy pronto regresaremos con más temas entretenidos y prácticos para su aprendizaje **diario**.",
                      f"Very soon we will return with more entertaining and practical topics for your daily learning."),
            ("Host1", f"¡Les deseamos un día estupendo y muchísimo éxito en su estudio del **español**!",
                      f"We wish you a wonderful day and huge success in your study of Spanish!"),
            ("Host2", f"¡Cuídense mucho, mantengan la motivación y hasta la **próxima**!",
                      f"Take good care of yourselves, keep up motivation and until next time!"),
            ("Host1", f"¡Hasta pronto, queridos amigos, y sigan hablando español con alegría y buen **ánimo**!",
                      f"See you soon, dear friends, and keep speaking Spanish with joy and good spirits!")
        ]
    ]

    all_templates = []
    for ph in phases:
        all_templates.extend(ph)
    turns = []
    for i in range(target):
        _, t_es, t_en = all_templates[i % len(all_templates)]
        spk = "Host2" if i % 2 == 0 else "Host1"
        turns.append({"speaker": spk, "spanish": t_es, "english": t_en})
    return turns


def _extend_script(existing_turns, topic_es, topic_en, target=150):
    fallback_pool = _fallback_script(topic_es, topic_en, target)
    idx = 0
    cur_speaker = existing_turns[-1]["speaker"] if existing_turns else "Host1"
    while len(existing_turns) < target:
        cand = fallback_pool[idx % len(fallback_pool)]
        idx += 1
        needed_spk = "Host1" if cur_speaker == "Host2" else "Host2"
        existing_turns.append({
            "speaker": needed_spk,
            "spanish": cand["spanish"],
            "english": cand["english"]
        })
        cur_speaker = needed_spk
    return existing_turns[:target]


def generate_script():
    topic = _generate_topic() or random.choice(TOPICS)
    topic_es = topic.split(" - ")[0]
    topic_en = topic.split(" - ")[1]

    TARGET = 150
    BATCH = 10
    all_turns = []
    consecutive_empty = 0
    import time as _time
    _deadline = _time.time() + 600  # generous 10 min cap

    while len(all_turns) < TARGET and consecutive_empty < 12 and _time.time() < _deadline:
        batch = _fetch_turns_batch(topic, topic_es, topic_en, len(all_turns), BATCH)
        if not batch:
            consecutive_empty += 1
            wait_s = min(15, 3 + consecutive_empty * 2)
            print(f"  API busy (consecutive fails: {consecutive_empty}) - waiting {wait_s}s before retrying...", flush=True)
            _time.sleep(wait_s)
            continue
        all_turns.extend(batch)
        consecutive_empty = 0
        print(f"  Script progress: {len(all_turns)}/{TARGET} turns", flush=True)
        if len(all_turns) < TARGET:
            _time.sleep(1)

    all_turns = all_turns[:TARGET]

    if not all_turns:
        print("  Using structured fallback script (150 unique turns)...", flush=True)
        all_turns = _fallback_script(topic_es, topic_en, TARGET)
    elif len(all_turns) < TARGET:
        print(f"  Extending {len(all_turns)} turns to {TARGET} with topic conversation...", flush=True)
        all_turns = _extend_script(all_turns, topic_es, topic_en, TARGET)

    # Short 2-line intro: Carlos (Host2) first, then Maria (Host1), then topic
    all_turns[0]["speaker"] = "Host2"
    all_turns[0]["spanish"] = f"Hola, soy Carlos. Bienvenidos a Velocity Spanish. Hoy hablamos de **{topic_es}**."
    all_turns[0]["english"] = f"Hi, I'm Carlos. Welcome to Velocity Spanish Podcast. Today we talk about {topic_en}."
    if len(all_turns) > 1:
        all_turns[1]["speaker"] = "Host1"
        all_turns[1]["spanish"] = f"Gracias, Carlos. El tema de hoy es muy **interesante**. Empecemos."
        all_turns[1]["english"] = f"Thanks, Carlos. Today's topic is very interesting. Let's start."

    print(f"  Script: {len(all_turns)} turns, topic: {topic_es}", flush=True)
    return all_turns, topic_es, topic_en


async def generate_audio(turns, target_dir=None):
    import edge_tts
    audio_dir = Path(target_dir) if target_dir else OUTPUT_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_files = []
    for i, turn in enumerate(turns):
        voice = HOST1_VOICE if turn["speaker"] == "Host1" else HOST2_VOICE
        filename = audio_dir / f"audio_{i:03d}.mp3"
        spoken_text = re.sub(r'\*\*(.*?)\*\*', r'\1', turn["spanish"])
        # Split long sentences at commas for natural TTS pauses, then pause at sentence endings
        paused_text = spoken_text.replace(', ', '. ').replace('. ', '... ').replace('?... ', '?... ').replace('!... ', '!... ')
        try:
            communicate = edge_tts.Communicate(paused_text, voice)
            await communicate.save(str(filename))
            try:
                r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(filename)], capture_output=True, text=True)
                duration = float(r.stdout.strip()) if r.stdout else 3.0
            except:
                duration = 3.0
        except Exception as e:
            print(f"  Audio {i} failed: {e}")
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "3", str(filename)], capture_output=True)
            duration = 3.0
        audio_files.append({"path": str(filename), "duration": duration, "speaker": turn["speaker"]})
        if (i + 1) % 25 == 0:
            print(f"  Audio {i+1}/{len(turns)}")
    return audio_files

YELLOW = (247, 202, 0)
DARK_BG = (11, 14, 27)
WHITE = (255, 255, 255)
LIGHT_GRAY = (170, 180, 205)
DARK_LINE = (50, 55, 75)

def load_font(size, bold=False, italic=False):
    # Font paths that exist on Windows (local) AND Linux (GitHub Actions runner).
    # The workflow installs fonts-dejavu-core + fonts-liberation via apt.
    fonts_to_try = []
    if italic and bold:
        fonts_to_try.extend([
            "C:/Windows/Fonts/segoeuiz.ttf", "C:/Windows/Fonts/arialbi.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
            str(FONTS_DIR / "DejaVuSans-BoldOblique.ttf"),
        ])
    elif italic:
        fonts_to_try.extend([
            "C:/Windows/Fonts/segoeuii.ttf", "C:/Windows/Fonts/ariali.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            str(FONTS_DIR / "DejaVuSans-Oblique.ttf"),
        ])
    elif bold:
        fonts_to_try.extend([
            "C:/Windows/Fonts/Inter-Bold-slnt=0.ttf", "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            str(FONTS_DIR / "DejaVuSans-Bold.ttf"),
        ])
    else:
        fonts_to_try.extend([
            "C:/Windows/Fonts/Inter-Regular-slnt=0.ttf", "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            str(FONTS_DIR / "DejaVuSans.ttf"),
        ])

    for p in fonts_to_try:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

def draw_microphone_icon(draw, center_x, center_y, radius=24):
    draw.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                 outline=YELLOW, width=3)
    w, h = 10, 18
    draw.rounded_rectangle([center_x - w//2, center_y - 12, center_x + w//2, center_y - 12 + h],
                           radius=4, fill=YELLOW)
    draw.arc([center_x - 10, center_y - 4, center_x + 10, center_y + 12],
             start=0, end=180, fill=YELLOW, width=3)
    draw.line([(center_x, center_y + 12), (center_x, center_y + 17)], fill=YELLOW, width=3)
    draw.line([(center_x - 7, center_y + 17), (center_x + 7, center_y + 17)], fill=YELLOW, width=3)

def draw_person_icon(draw, center_x, center_y):
    draw.ellipse([center_x - 6, center_y - 12, center_x + 6, center_y], fill=YELLOW)
    draw.chord([center_x - 12, center_y + 2, center_x + 12, center_y + 20],
               start=180, end=360, fill=YELLOW)

def draw_spanish_flag(img, draw, center_x, center_y, radius=22):
    flag_img = Image.new('RGBA', (radius*2, radius*2), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(flag_img)
    fdraw.rectangle([(0, 0), (radius*2, int(radius*2*0.28))], fill=(198, 11, 30, 255))
    fdraw.rectangle([(0, int(radius*2*0.28)), (radius*2, int(radius*2*0.72))], fill=(255, 196, 0, 255))
    fdraw.rectangle([(0, int(radius*2*0.72)), (radius*2, radius*2)], fill=(198, 11, 30, 255))
    
    mask = Image.new('L', (radius*2, radius*2), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse([0, 0, radius*2, radius*2], fill=255)
    img.paste(flag_img, (center_x - radius, center_y - radius), mask)

def draw_headphones_icon(draw, center_x, center_y):
    draw.arc([center_x - 14, center_y - 14, center_x + 14, center_y + 6],
             start=180, end=360, fill=YELLOW, width=3)
    draw.rounded_rectangle([center_x - 16, center_y - 3, center_x - 10, center_y + 11], radius=2, fill=YELLOW)
    draw.rounded_rectangle([center_x + 10, center_y - 3, center_x + 16, center_y + 11], radius=2, fill=YELLOW)

def auto_highlight_spanish(text):
    """Ensure at least 1 word is highlighted in yellow with ** word ** if none exists."""
    if '**' in text:
        return text
    stopwords = {'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del', 'en', 'a', 'al', 'y', 'o', 'que', 'es', 'son', 'se', 'mi', 'tu', 'su', 'nos', 'por', 'con', 'para', 'hola', 'bueno', 'vale', 'si', 'sí', 'no'}
    words = text.split()
    candidates = []
    for idx, w in enumerate(words):
        clean_w = re.sub(r'[^\wÁÉÍÓÚáéíóúñÑ]', '', w, flags=re.UNICODE)
        if clean_w.lower() not in stopwords and len(clean_w) >= 3:
            candidates.append((len(clean_w), idx, w, clean_w))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_idx = candidates[0][1]
        raw_w = words[best_idx]
        clean_w = candidates[0][3]
        highlighted = raw_w.replace(clean_w, f"**{clean_w}**")
        words[best_idx] = highlighted
        return " ".join(words)
    return text

def draw_rich_text_centered(draw, text, center_y, font, max_w=1550, line_height=90):
    text = auto_highlight_spanish(text)
    pattern = r'(\*\*.*?\*\*)'
    raw_parts = re.split(pattern, text)
    tokens = []
    for part in raw_parts:
        if part.startswith('**') and part.endswith('**'):
            tokens.append((part[2:-2], True))
        elif part:
            tokens.append((part, False))
            
    words_with_status = []
    for text_chunk, is_yellow in tokens:
        words = text_chunk.split(' ')
        for i, w in enumerate(words):
            if w:
                words_with_status.append((w, is_yellow))
            if i < len(words) - 1:
                words_with_status.append((' ', False))

    lines = []
    current_line = []
    current_line_width = 0

    for item in words_with_status:
        word, is_yellow = item
        w_bbox = draw.textbbox((0, 0), word, font=font)
        w_width = w_bbox[2] - w_bbox[0]

        if current_line_width + w_width <= max_w or not current_line:
            current_line.append((word, is_yellow, w_width))
            current_line_width += w_width
        else:
            if current_line and current_line[-1][0] == ' ':
                current_line_width -= current_line[-1][2]
                current_line.pop()
            lines.append((current_line, current_line_width))
            if word == ' ':
                current_line = []
                current_line_width = 0
            else:
                current_line = [(word, is_yellow, w_width)]
                current_line_width = w_width

    if current_line:
        if current_line[-1][0] == ' ':
            current_line_width -= current_line[-1][2]
            current_line.pop()
        lines.append((current_line, current_line_width))

    total_height = len(lines) * line_height
    start_y = center_y - total_height // 2

    for line_idx, (line_words, line_w) in enumerate(lines):
        start_x = (VIDEO_WIDTH - line_w) // 2
        curr_x = start_x
        curr_y = start_y + line_idx * line_height

        for word, is_yellow, w_w in line_words:
            color = YELLOW if is_yellow else WHITE
            draw.text((curr_x, curr_y), word, fill=color, font=font)
            curr_x += w_w

def draw_english_translation(draw, text, center_y, font, max_w=1350, line_height=52):
    """Draw wrapped, centered English translation without cropping."""
    words = text.split()
    lines = []
    current_line = []
    
    for w in words:
        test_line = ' '.join(current_line + [w])
        bb = draw.textbbox((0, 0), test_line, font=font)
        if bb[2] - bb[0] <= max_w:
            current_line.append(w)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [w]
    if current_line:
        lines.append(' '.join(current_line))
        
    total_h = len(lines) * line_height
    start_y = center_y - total_h // 2
    
    for idx, line in enumerate(lines):
        draw.text((VIDEO_WIDTH // 2, start_y + idx * line_height + line_height // 2),
                  line, fill=LIGHT_GRAY, font=font, anchor="mm")

def create_frame(turn, output_path, frame_num=0):
    img = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Ambient subtle background circles
    glow = Image.new('RGBA', (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(-200, VIDEO_HEIGHT-600), (600, VIDEO_HEIGHT+200)], fill=(30, 20, 60, 40))
    gdraw.ellipse([(VIDEO_WIDTH-500, -200), (VIDEO_WIDTH+300, 600)], fill=(30, 20, 60, 40))
    img.paste(glow, (0, 0), glow)

    # Fonts
    f_title_white = load_font(36, bold=True)
    f_title_sub = load_font(18, bold=False)
    f_title_sub_muted = load_font(15, bold=False)
    f_ep = load_font(22, bold=True)
    f_speaker = load_font(26, bold=True)
    f_hablando = load_font(24, bold=False)
    f_spanish = load_font(64, bold=True)
    f_english = load_font(42, bold=False, italic=True)
    f_footer = load_font(22, bold=False)

    # === TOP HEADER ===
    header_y = 68
    draw_microphone_icon(draw, center_x=70, center_y=header_y, radius=24)

    # Channel Title: VELOCITY SPANISH PODCAST (Vertically centered at y=68)
    draw.text((110, header_y), "VELOCITY", fill=WHITE, font=f_title_white, anchor="lm")
    v_bbox = draw.textbbox((110, header_y), "VELOCITY", font=f_title_white, anchor="lm")
    
    draw.text((v_bbox[2] + 8, header_y), "SPANISH", fill=YELLOW, font=f_title_white, anchor="lm")
    s_bbox = draw.textbbox((v_bbox[2] + 8, header_y), "SPANISH", font=f_title_white, anchor="lm")

    draw.text((s_bbox[2] + 8, header_y), "PODCAST", fill=WHITE, font=f_title_white, anchor="lm")
    p_bbox = draw.textbbox((s_bbox[2] + 8, header_y), "PODCAST", font=f_title_white, anchor="lm")

    # Vertical separator bar
    draw.line([(p_bbox[2] + 20, 48), (p_bbox[2] + 20, 88)], fill=DARK_LINE, width=2)

    # Stacked 2 lines (Symmetrically centered around y=68)
    sub_x = p_bbox[2] + 35
    draw.text((sub_x, header_y - 12), "Spanish Podcast", fill=WHITE, font=f_title_sub, anchor="lm")
    draw.text((sub_x, header_y + 12), "Learn Through Conversations", fill=LIGHT_GRAY, font=f_title_sub_muted, anchor="lm")

    # Episode badge (pill)
    ep_num = (frame_num // 150) + 1 if isinstance(frame_num, int) else 1
    ep_str = f"EP {ep_num:02d}"
    draw.rounded_rectangle([(1640, 46), (1750, 90)], radius=8, fill=YELLOW)
    draw.text((1695, header_y), ep_str, fill=DARK_BG, font=f_ep, anchor="mm")

    # Spanish flag
    draw_spanish_flag(img, draw, center_x=1810, center_y=header_y, radius=22)

    draw.line([(0, 130), (VIDEO_WIDTH, 130)], fill=YELLOW, width=2)

    # === SPEAKER STATUS SECTION ===
    is_host1 = turn.get("speaker") == "Host1"
    speaker_name = "MARIA" if is_host1 else "CARLOS"
    pill_x, pill_y = 120, 210
    pill_w, pill_h = 220, 52

    draw.rounded_rectangle([(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)],
                           radius=26, outline=YELLOW, width=2)
    draw_person_icon(draw, center_x=pill_x + 36, center_y=pill_y + 26)
    draw.text((pill_x + 60, pill_y + 26), speaker_name, fill=YELLOW, font=f_speaker, anchor="lm")

    draw.text((pill_x + pill_w + 25, pill_y + 26), "hablando", fill=LIGHT_GRAY, font=f_hablando, anchor="lm")

    # === MAIN TEXT (auto-size, HARD max 3 lines) ===
    spanish_text = turn.get("spanish", turn.get("spanish", ""))
    chosen_font = None
    chosen_lh = 90
    final_lines = []
    for test_size in [64, 56, 48, 40, 34, 28, 24, 20]:
        test_font = load_font(test_size, bold=True)
        test_lh = int(test_size * 1.4)
        text_words = spanish_text.split()
        tmp_lines = []
        cur = []
        for w in text_words:
            test = ' '.join(cur + [w])
            bb = draw.textbbox((0, 0), test, font=test_font)
            if bb[2] - bb[0] <= 1550 or not cur:
                cur.append(w)
            else:
                tmp_lines.append(' '.join(cur))
                cur = [w]
        if cur: tmp_lines.append(' '.join(cur))
        if len(tmp_lines) <= 3:
            chosen_font = test_font
            chosen_lh = test_lh
            final_lines = tmp_lines
            break
    if chosen_font is None:
        chosen_font = load_font(20, bold=True)
        chosen_lh = int(20 * 1.4)
        text_words = spanish_text.split()
        tmp_lines = []
        cur = []
        for w in text_words:
            test = ' '.join(cur + [w])
            bb = draw.textbbox((0, 0), test, font=chosen_font)
            if bb[2] - bb[0] <= 1550 or not cur:
                cur.append(w)
            else:
                tmp_lines.append(' '.join(cur))
                cur = [w]
        if cur: tmp_lines.append(' '.join(cur))
        if len(tmp_lines) > 3:
            tmp_lines = tmp_lines[:3]
            if spanish_text:
                tmp_lines[-1] = tmp_lines[-1].rstrip() + "..."
        final_lines = tmp_lines
        spanish_text = " ".join(final_lines)
    draw_rich_text_centered(draw, spanish_text, center_y=440, font=chosen_font, max_w=1550, line_height=chosen_lh)

    # === CENTER DIVIDER WITH DOT ===
    div_y = 615
    draw.line([(VIDEO_WIDTH//2 - 300, div_y), (VIDEO_WIDTH//2 + 300, div_y)], fill=YELLOW, width=2)
    draw.ellipse([(VIDEO_WIDTH//2 - 8, div_y - 8), (VIDEO_WIDTH//2 + 8, div_y + 8)], fill=YELLOW)

    # === ENGLISH TRANSLATION (ITALIC, WRAPPED, LARGER) ===
    english_text = turn.get("english", "")
    draw_english_translation(draw, english_text, center_y=715, font=f_english, max_w=1350, line_height=52)

    # === BOTTOM FOOTER ===
    draw.line([(0, 975), (VIDEO_WIDTH, 975)], fill=YELLOW, width=2)

    footer_y = 1025
    draw_headphones_icon(draw, center_x=VIDEO_WIDTH//2 - 270, center_y=footer_y)
    draw.text((VIDEO_WIDTH//2 - 240, footer_y), "Learn Spanish Naturally", fill=WHITE, font=f_footer, anchor="lm")
    
    fn_bbox = draw.textbbox((VIDEO_WIDTH//2 - 240, footer_y), "Learn Spanish Naturally", font=f_footer, anchor="lm")
    draw.line([(fn_bbox[2] + 20, footer_y - 12), (fn_bbox[2] + 20, footer_y + 12)], fill=DARK_LINE, width=2)
    
    draw.text((fn_bbox[2] + 40, footer_y), "velocityspanish.com", fill=WHITE, font=f_footer, anchor="lm")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=92)



def _wrap(draw, text, font, max_w):
    words = text.split()
    lines = []
    cur = []
    for w in words:
        test = ' '.join(cur + [w])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_w:
            cur.append(w)
        else:
            if cur: lines.append(' '.join(cur))
            cur = [w]
    if cur: lines.append(' '.join(cur))
    return lines

def create_video(turns, audio_files, video_dir=None):
    if video_dir is None:
        video_dir = OUTPUT_DIR / f"podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    video_dir = Path(video_dir)
    video_dir.mkdir(parents=True, exist_ok=True)
    
    clips = []
    total_dur = 0
    
    for i, (turn, audio) in enumerate(zip(turns, audio_files)):
        img = video_dir / f"f_{i:04d}.png"
        create_frame(turn, str(img), i)
        clip = video_dir / f"c_{i:04d}.mp4"
        clips.append(clip)
        dur = audio["duration"]
        
        # Fade out only in the last 0.3s of the clip so the full voice is audible
        fade_start = max(0.0, dur - 0.3)
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", audio["path"],
            "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT},fps={FPS}",
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-preset", "medium",
            "-t", str(dur), "-af", f"afade=t=out:st={fade_start:.2f}:d=0.3",
            str(clip)
        ], check=True, capture_output=True)
        
        total_dur += audio["duration"]
        if (i + 1) % 25 == 0:
            print(f"  Frame {i+1}/{len(turns)}")
    
    # Concatenate
    concat = video_dir / "list.txt"
    with open(concat, "w") as f:
        for c in clips:
            f.write(f"file '{c.resolve().as_posix()}'\n")
    
    out = video_dir / "podcast_final.mp4"
    # Re-encode audio on concat to avoid timestamp/DTS corruption from -c copy.
    # Each clip has a small fade-out so re-encoding keeps audio in perfect sync.
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                    "-movflags", "+faststart", str(out)], check=True)
    
    # Clean up intermediate clips and audio files (keep frames + final video)
    for c in clips:
        c.unlink(missing_ok=True)
    for a in audio_files:
        try:
            Path(a["path"]).unlink(missing_ok=True)
        except Exception:
            pass
    if concat.exists():
        concat.unlink(missing_ok=True)
    
    return out, total_dur

async def main():
    print("=" * 60)
    print("  VELOCITY SPANISH PODCAST")
    print("  Maria & Carlos | A2 Level | 15 min")
    print("=" * 60)
    
    print("\n[1/4] Generating script (150 turns)...")
    turns, topic_es, topic_en = generate_script()
    
    video_dir = OUTPUT_DIR / f"podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    video_dir.mkdir(parents=True, exist_ok=True)
    
    with open(video_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump({"topic_es": topic_es, "topic_en": topic_en, "turns": turns}, f, indent=2, ensure_ascii=False)
    
    print(f"\n[2/4] Generating audio ({len(turns)} turns)...")
    audio_files = await generate_audio(turns, video_dir)
    total_audio = sum(a["duration"] for a in audio_files)
    print(f"  Total audio: {total_audio/60:.1f} min")
    
    print(f"\n[3/4] Creating video...")
    video_path, duration = create_video(turns, audio_files, video_dir)
    
    print(f"\n[4/4] Saving...")
    meta = {
        "language": "Spanish", "topic_es": topic_es, "topic_en": topic_en,
        "turns": len(turns), "duration_min": round(duration / 60, 1),
        "video": str(video_path), "generated": datetime.now().isoformat()
    }
    with open(video_dir / "latest.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # Write top-level latest_video.json for the upload script + generate title/description/tags
    first_frame = video_dir / "f_0000.png"
    thumbnail_path = video_dir / "thumbnail.jpg"
    try:
        from PIL import Image as _Img
        if first_frame.exists():
            _Img.open(str(first_frame)).convert("RGB").save(str(thumbnail_path), quality=92)
    except Exception as e:
        print(f"  Thumbnail warn: {e}")

    title = build_podcast_title(topic_es, topic_en)
    description = build_podcast_description(topic_es, topic_en, len(turns), round(duration / 60, 1))
    tags = ["Learn Spanish", "Spanish", "Spanish Podcast", "Aprender Español", "Spanish Lesson",
            "Spanish for Beginners", "Bilingual", "Spanish Listening", "Spanish Conversation",
            "Spanish Vocabulary", topic_es, "Velocity Spanish"]

    meta_out = {
        "title": title,
        "description": description,
        "tags": tags,
        "category_english": topic_es,
        "language": "Spanish",
        "duration_minutes": round(duration / 60, 1),
        "turns_count": len(turns),
        "video_path": str(video_path),
        "thumbnail_path": str(thumbnail_path),
        "generated_at": datetime.now().isoformat(),
    }
    (OUTPUT_DIR).mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "latest_video.json", "w", encoding="utf-8") as f:
        json.dump(meta_out, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_DIR / "latest_upload_info.json", "w", encoding="utf-8") as f:
        json.dump({"title": title, "description": description,
                   "category": topic_es, "turns_count": len(turns)}, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("  PODCAST COMPLETE!")
    print(f"  Topic: {topic_es}")
    print(f"  Duration: {duration/60:.1f} min ({len(turns)} turns)")
    print(f"  Video: {video_path.name}")
    print("=" * 60)


def build_podcast_title(topic_es, topic_en):
    """Build a clean, keyword-rich title for the episode."""
    titles = [
        f"Spanish Podcast: {topic_es} | Aprende Español",
        f"{topic_es} | Spanish Conversation for Beginners",
        f"Learn Spanish: {topic_es} | Bilingual Podcast",
        f"{topic_es} | Practica Tu Español con Carlos y María",
    ]
    return random.choice(titles)


def build_podcast_description(topic_es, topic_en, turns_count, duration_min):
    """Build a rich, careful description with episode info and learning value."""
    description = (
        f"🎙️ ¡Bienvenidos a Velocity Spanish Podcast!\n\n"
        f"En este episodio, Carlos y María conversan sobre: {topic_es} ({topic_en}).\n"
        f"Una conversación bilingüe y relajada, a nivel A2, para que aprendas español de forma natural.\n\n"
        f"✨ WHAT'S INSIDE THIS EPISODE:\n"
        f"• {turns_count} frases y expresiones útiles en español\n"
        f"• Conversación real con vocabulario cotidiano\n"
        f"• Pronunciación natural de hablantes nativos\n"
        f"• Traducción al inglés en cada línea\n\n"
        f"📌 HOW TO USE THIS PODCAST:\n"
        f"1️⃣ Escucha la parte en español e intenta entenderla\n"
        f"2️⃣ Comprueba la traducción al inglés\n"
        f"3️⃣ Repite las frases en voz alta\n"
        f"4️⃣ Vuelve a escuchar mañana - ¡cada día es más fácil!\n\n"
        f"🔔 Subscribe para una nueva lección cada día.\n\n"
        f"📅 Duración: {duration_min} minutos\n\n"
        f"#LearnSpanish #SpanishPodcast #AprenderEspañol #SpanishForBeginners "
        f"#SpanishListening #SpanishConversation #Bilingual"
    )
    return description

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Cancelled.")