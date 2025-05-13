import json
import os
from copy import copy
from functools import cache

import requests
import torch
import torchaudio
from tqdm import tqdm
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

VOICES_URL = "http://localhost:8000/v1/tts/piper/voices"
TTS_URL = "http://localhost:8000/v1/tts/piper/speak"

# noinspection SpellCheckingInspection
TEST_SENTENCES = {
    "en_US": "Good morning everyone, I’m absolutely delighted to welcome you all to this year’s international science symposium, where we’ll explore innovation, collaboration, and the future of technology together.",
    "ar_JO": "صباح الخير جميعًا، أنا سعيد للغاية بترحيبكم جميعًا في ندوة العلوم الدولية لهذا العام، حيث سنستكشف معًا الابتكار والتعاون ومستقبل التكنولوجيا.",
    "ca_ES": "Bon dia a tothom, estic absolutament encantat de donar-vos la benvinguda al simposi internacional de ciència d'aquest any, on explorarem junts la innovació, la col·laboració i el futur de la tecnologia.",
    "cs_CZ": "Dobré ráno všem, jsem naprosto potěšen, že vás mohu přivítat na letošním mezinárodním vědeckém sympoziu, kde společně prozkoumáme inovace, spolupráci a budoucnost technologií.",
    "cy_GB": "Bore da bawb, rwy'n hynod falch o'ch croesawu i gyd i symposiwm gwyddoniaeth rhyngwladol eleni, lle byddwn yn archwilio arloesi, cydweithredu a dyfodol technoleg gyda'n gilydd.",
    "da_DK": "Godmorgen alle sammen, jeg er absolut begejstret for at byde jer alle velkommen til dette års internationale videnskabssymposium, hvor vi sammen vil udforske innovation, samarbejde og teknologiens fremtid.",
    "de_DE": "Guten Morgen allerseits, ich freue mich sehr, Sie alle zum diesjährigen internationalen Wissenschaftssymposium willkommen zu heißen, bei dem wir gemeinsam Innovation, Zusammenarbeit und die Zukunft der Technologie erkunden werden.",
    "el_GR": "Καλημέρα σε όλους, είμαι απόλυτα ενθουσιασμένος που σας καλωσορίζω στο φετινό διεθνές επιστημονικό συμπόσιο, όπου θα εξερευνήσουμε μαζί την καινοτομία, τη συνεργασία και το μέλλον της τεχνολογίας.",
    "en_GB": "Good morning everyone, I’m absolutely delighted to welcome you all to this year’s international science symposium, where we’ll explore innovation, collaboration, and the future of technology together.",
    "es_ES": "Buenos días a todos, estoy absolutamente encantado de darles la bienvenida al simposio internacional de ciencia de este año, donde exploraremos juntos la innovación, la colaboración y el futuro de la tecnología.",
    "es_MX": "Buenos días a todos, estoy absolutamente encantado de darles la bienvenida al simposio internacional de ciencia de este año, donde exploraremos juntos la innovación, la colaboración y el futuro de la tecnología.",
    "fa_IR": "صبح بخیر به همه، من بسیار خوشحالم که همه شما را در سمپوزیوم بین‌المللی علمی امسال خوش‌آمد می‌گویم، جایی که با هم نوآوری، همکاری و آینده فناوری را بررسی خواهیم کرد.",
    "fi_FI": "Hyvää huomenta kaikille, olen todella iloinen saadessani toivottaa teidät kaikki tervetulleiksi tämän vuoden kansainväliseen tiedesymposiumiin, jossa tutkimme yhdessä innovaatiota, yhteistyötä ja teknologian tulevaisuutta.",
    "fr_FR": "Bonjour à tous, je suis absolument ravi de vous accueillir tous au symposium scientifique international de cette année, où nous explorerons ensemble l'innovation, la collaboration et l'avenir de la technologie.",
    "hu_HU": "Jó reggelt mindenkinek, rendkívül örülök, hogy üdvözölhetem Önöket az idei nemzetközi tudományos szimpóziumon, ahol együtt fogjuk felfedezni az innovációt, az együttműködést és a technológia jövőjét.",
    "is_IS": "Góðan daginn allir saman, ég er afar ánægður með að bjóða ykkur öll velkomin á alþjóðlega vísindaráðstefnu ársins, þar sem við munum saman kanna nýsköpun, samstarf og framtíð tækni.",
    "it_IT": "Buongiorno a tutti, sono assolutamente lieto di darvi il benvenuto al simposio scientifico internazionale di quest'anno, dove esploreremo insieme l'innovazione, la collaborazione e il futuro della tecnologia.",
    "ka_GE": "დილა მშვიდობისა ყველას, ძალიან მიხარია, რომ გესალმებით წლევანდელ საერთაშორისო სამეცნიერო სიმპოზიუმზე, სადაც ერთად შევისწავლით ინოვაციას, თანამშრომლობას და ტექნოლოგიის მომავალს.",
    "kk_KZ": "Қайырлы таң, баршаңызға! Биылғы халықаралық ғылыми симпозиумға қош келдіңіздер, мұнда біз бірге инновацияны, ынтымақтастықты және технологияның болашағын зерттейміз.",
    "lb_LU": "Gudde Moien alleguer, ech sinn immens frou Iech all op dem internationale Wëssenschaftssymposium dëst Joer wëllkomm ze heeschen, wou mir zesumme Innovatioun, Zesummenaarbecht an d’Zukunft vun der Technologie entdecken.",
    "ne_NP": "सुप्रभात सबैलाई, म तपाईंहरू सबैलाई यस वर्षको अन्तर्राष्ट्रिय विज्ञान संगोष्ठीमा स्वागत गर्न पाउँदा अत्यन्तै खुशी छु, जहाँ हामी एकसाथ नवप्रवर्तन, सहकार्य र प्रविधिको भविष्य अन्वेषण गर्नेछौं।",
    "nl_BE": "Goedemorgen allemaal, ik ben ontzettend blij jullie allemaal te mogen verwelkomen op het internationale wetenschappelijk symposium van dit jaar, waar we samen innovatie, samenwerking en de toekomst van technologie zullen verkennen.",
    "nl_NL": "Goedemorgen allemaal, ik ben ontzettend blij jullie allemaal te mogen verwelkomen op het internationale wetenschappelijk symposium van dit jaar, waar we samen innovatie, samenwerking en de toekomst van technologie zullen verkennen.",
    "pl_PL": "Dzień dobry wszystkim, z ogromną radością witam was na tegorocznym międzynarodowym sympozjum naukowym, gdzie wspólnie będziemy odkrywać innowacje, współpracę i przyszłość technologii.",
    "pt_BR": "Bom dia a todos, estou absolutamente encantado em dar as boas-vindas a todos vocês ao simpósio internacional de ciência deste ano, onde exploraremos juntos a inovação, a colaboração e o futuro da tecnologia.",
    "pt_PT": "Bom dia a todos, é com grande prazer que vos dou as boas-vindas ao simpósio internacional de ciência deste ano, onde exploraremos juntos a inovação, a colaboração e o futuro da tecnologia.",
    "ro_RO": "Bună dimineața tuturor, sunt absolut încântat să vă urez bun venit la simpozionul internațional de știință din acest an, unde vom explora împreună inovația, colaborarea și viitorul tehnologiei.",
    "ru_RU": "Всем доброе утро! Я чрезвычайно рад приветствовать вас на Международном научном симпозиуме этого года, где мы вместе изучим инновации, сотрудничество и будущее технологий.",
    "sk_SK": "Dobré ráno všetkým, som nesmierne potešený, že vás môžem privítať na tohtoročnom medzinárodnom vedeckom sympóziu, kde budeme spolu skúmať inovácie, spoluprácu a budúcnosť technológií.",
    "sl_SI": "Dobro jutro vsem, z velikim veseljem vas pozdravljam na letošnjem mednarodnem znanstvenem simpoziju, kjer bomo skupaj raziskovali inovacije, sodelovanje in prihodnost tehnologije.",
    "sr_RS": "Dobro jutro svima, izuzetno mi je drago što mogu da vas pozdravim na ovogodišnjem međunarodnom naučnom simpozijumu, gde ćemo zajedno istraživati inovacije, saradnju i budućnost tehnologije.",
    "sv_SE": "God morgon allihopa, jag är verkligen glad att få välkomna er alla till årets internationella vetenskapssymposium, där vi tillsammans ska utforska innovation, samarbete och teknikens framtid.",
    "sw_CD": "Habari za asubuhi nyote, nina furaha sana kuwakaribisha nyote kwenye kongamano la kimataifa la sayansi la mwaka huu, ambapo tutachunguza kwa pamoja ubunifu, ushirikiano, na mustakabali wa teknolojia.",
    "tr_TR": "Herkese günaydın, bu yılki uluslararası bilim sempozyumuna hepiniz hoş geldiniz demekten büyük mutluluk duyuyorum. Birlikte yenilikçiliği, iş birliğini ve teknolojinin geleceğini keşfedeceğiz.",
    "uk_UA": "Доброго ранку всім, я щиро радий вітати вас на цьогорічному міжнародному науковому симпозіумі, де ми разом досліджуватимемо інновації, співпрацю та майбутнє технологій.",
}


SYSTEM_PROMPT = (
    "Determine the gender of the speaker in the provided audio. "
    "Your task is to identify whether the speaker is male or female. "
    "Reply only with 'male' or 'female'. "
    "You have to respond, even when unsure."
)


def get_voices():
    res = requests.get(VOICES_URL)
    return res.json()["voices"]


def generate_audio(text, voice_id):
    return requests.post(TTS_URL, json={"text": text, "voice": voice_id}).content


@cache
def get_model():
    model_name = "alefiury/wav2vec2-large-xlsr-53-gender-recognition-librispeech"
    feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)
    model = AutoModelForAudioClassification.from_pretrained(model_name)
    model.eval()
    return model, feature_extractor


def classify_gender(audio_bytes):
    model, feature_extractor = get_model()

    # Decode PCM bytes
    audio_tensor = (
        torch.frombuffer(copy(audio_bytes), dtype=torch.int16).float() / 32768.0
    )
    audio_tensor = audio_tensor.unsqueeze(0)  # (1, samples)

    # Resample to 16kHz
    resampler = torchaudio.transforms.Resample(orig_freq=22050, new_freq=16000)
    audio_tensor = resampler(audio_tensor)

    # Extract features
    inputs = feature_extractor(
        audio_tensor.squeeze().numpy(), sampling_rate=16000, return_tensors="pt"
    )

    # Inference
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=1).squeeze()
        pred = torch.argmax(probs).item()
        label = model.config.id2label[pred]

    return label


def main():
    voices = get_voices()

    genders = {}
    if os.path.exists("data/piper_gender.json"):
        with open("data/piper_gender.json", "r") as f:
            genders = json.load(f)

    for voice in tqdm(voices, desc="Processing voices"):
        if voice["gender"] == "unknown" and voice["language"] in TEST_SENTENCES:
            try:
                audio = generate_audio(TEST_SENTENCES[voice["language"]], voice["id"])
                genders[voice["id"]] = classify_gender(audio)
                print(f"\n{voice['id']}: {genders[voice['id']]}")
            except Exception as e:
                print(f"Error processing {voice['id']}: {e}")

    with open("data/piper_gender.json", "w") as f:
        json.dump(genders, f, indent=2)


if __name__ == "__main__":
    main()
