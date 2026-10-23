// Phase 16: hands the microphone's samples to the page in blocks of ~2000 (about 40 ms), where
// they are gathered and turned into a WAV when the recording ends. Served from 'self'.
class DictationProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.block = new Float32Array(2048)
    this.filled = 0
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (!channel) return true
    let read = 0
    while (read < channel.length) {
      const count = Math.min(channel.length - read, this.block.length - this.filled)
      this.block.set(channel.subarray(read, read + count), this.filled)
      this.filled += count
      read += count
      if (this.filled === this.block.length) {
        this.port.postMessage(this.block.slice())
        this.filled = 0
      }
    }
    return true
  }
}

registerProcessor('dictation-processor', DictationProcessor)
