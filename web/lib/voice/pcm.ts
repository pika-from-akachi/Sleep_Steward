export function downsampleTo16Khz(samples: Float32Array, sourceRate: number): Float32Array {
  if (sourceRate < 16000) throw new RangeError("录音采样率低于 16kHz");
  if (sourceRate === 16000) return samples.slice();

  const ratio = sourceRate / 16000;
  const output = new Float32Array(Math.floor(samples.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.max(start + 1, Math.floor((index + 1) * ratio));
    let sum = 0;
    for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
      sum += samples[sourceIndex];
    }
    output[index] = sum / (end - start);
  }
  return output;
}

export function floatSamplesToPcm16(samples: Float32Array): Uint8Array {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(index * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  }
  return bytes;
}

export function mergeFloatChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const merged = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

export function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}
