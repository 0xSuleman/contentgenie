import re

def getSpeechBlocks(whispered, silence_time=0.8):
    text_blocks, (st, et, txt) = [], (0,0,"")
    for i, seg in enumerate(whispered['segments']):
        if seg['start'] - et > silence_time:
            if txt: text_blocks.append([[st, et], txt])
            (st, et, txt) = (seg['start'], seg['end'], seg['text'])
        else: 
            et, txt = seg['end'], txt + seg['text']

    if txt: text_blocks.append([[st, et], txt]) # For last text block

    return text_blocks

def cleanWord(word):
    return re.sub(r'[^\w\s\-_"\'\']', '', word)

def interpolateTimeFromDict(word_position, d):
    for key, value in d.items():
        if key[0] <= word_position <= key[1]:
            return value
    return None

def getTimestampMapping(whisper_analysis):
    index = 0
    locationToTimestamp = {}
    for segment in whisper_analysis['segments']:
        for word in segment['words']:
            newIndex = index + len(word['text'])+1
            locationToTimestamp[(index, newIndex)] = word['end']
            index = newIndex
    return locationToTimestamp


def splitWordsBySize(words, maxCaptionSize):
    halfCaptionSize = maxCaptionSize / 2
    captions = []
    while words:
        caption = words[0]
        words = words[1:]
        while words and len(caption + ' ' + words[0]) <= maxCaptionSize:
            caption += ' ' + words[0]
            words = words[1:]
            if len(caption) >= halfCaptionSize and words:
                break
        captions.append(caption)
    return captions

def getCaptionsWithTime(transcriptions, maxCaptionSize=15, considerPunctuation=True):
    maxCaptionSize = max(1, int(maxCaptionSize or 15))
    all_words = [
        word
        for segment in transcriptions.get('segments', [])
        for word in segment.get('words', [])
        if str(word.get('text', '')).strip()
    ]
    if not all_words:
        return []

    time_splits = []
    current = []

    def flush():
        if not current:
            return
        text = ' '.join(str(word['text']).strip() for word in current).strip()
        if text:
            time_splits.append(((float(current[0]['start']), float(current[-1]['end'])), text))
        current.clear()

    for word in all_words:
        word_text = str(word['text']).strip()
        candidate = ' '.join([*(str(item['text']).strip() for item in current), word_text])
        if current and len(candidate) > maxCaptionSize:
            flush()

        current.append(word)
        ends_sentence = considerPunctuation and bool(re.search(r'[.!?][\"\']?$', word_text))
        if ends_sentence or len(current) >= 5:
            flush()

    flush()
    return time_splits


def getWordsWithTime(transcriptions):
    words = []
    for segment in transcriptions.get('segments', []):
        for word in segment.get('words', []):
            text = cleanWord(word.get('text', '')).strip()
            if text:
                words.append(((word['start'], word['end']), text))
    return words
