export interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

export interface SpeechRecognitionResultLike
  extends ArrayLike<SpeechRecognitionAlternativeLike> {
  isFinal: boolean;
}

export function finalSpeechTranscript(
  results: ArrayLike<SpeechRecognitionResultLike>,
): string {
  const finalSegments: string[] = [];

  for (let index = 0; index < results.length; index += 1) {
    const result = results[index];
    const transcript = result?.[0]?.transcript.trim();
    if (result?.isFinal && transcript) finalSegments.push(transcript);
  }

  return finalSegments.join(" ");
}
