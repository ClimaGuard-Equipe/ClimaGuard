#pragma once
#include <math.h>
#include <stdint.h>

// Raw ADC units describe the low-voltage waveform, never mains volts.
namespace PowerSignal {
struct Frame {
  float mean = 0, rms = 0, coherence = 0;
  bool valid = false;
  const char *error = "starting";
};

inline Frame analyze(const uint16_t *samples, const uint32_t *times, unsigned count) {
  Frame result;
  if (count < 120) return result;
  uint32_t span = times[count - 1] - times[0];
  if (span < 180000 || span > 350000) { result.error = "timing"; return result; }
  unsigned clipped = 0;
  double sum = 0;
  for (unsigned i = 0; i < count; ++i) {
    if (samples[i] < 20 || samples[i] > 4075) ++clipped;
    if (i && uint32_t(times[i] - times[i - 1]) > 12000) { result.error = "timing"; return result; }
    sum += samples[i];
  }
  result.mean = sum / count;
  double square = 0, sin50 = 0, cos50 = 0, sin60 = 0, cos60 = 0;
  for (unsigned i = 0; i < count; ++i) {
    double value = samples[i] - result.mean;
    double t = uint32_t(times[i] - times[0]) * .000001;
    square += value * value;
    sin50 += value * sin(314.1592653589793 * t); cos50 += value * cos(314.1592653589793 * t);
    sin60 += value * sin(376.9911184307752 * t); cos60 += value * cos(376.9911184307752 * t);
  }
  result.rms = sqrt(square / count);
  if (result.rms > 0) {
    double amplitude = 2 * sqrt(fmax(sin50*sin50 + cos50*cos50, sin60*sin60 + cos60*cos60)) / count;
    result.coherence = fmin(1.0, amplitude / (1.4142135623730951 * result.rms));
  }
  if (clipped > count / 50) { result.error = "clipped"; return result; }
  if (result.mean < 250 || result.mean > 3800) { result.error = "no_signal"; return result; }
  result.valid = true; result.error = "ok"; return result;
}

struct Detector {
  bool known = false, present = false;
  unsigned on = 0, off = 0;
  void reset() { known = false; on = off = 0; }
  void update(const Frame &frame, bool enabled, float reference) {
    if (!enabled || reference < 25 || !isfinite(reference) || !frame.valid) { reset(); return; }
    const float high = reference * .35f, low = reference * .20f;
    if (frame.rms >= high && frame.coherence >= .65f) {
      off = 0; if (on < 2) ++on;
      if (on >= 2) { known = true; present = true; }
    } else if (frame.rms <= low) {
      on = 0; if (off < 2) ++off;
      if (off >= 2) { known = true; present = false; }
    } else if (frame.rms >= high) {
      reset(); // Large random noise is not evidence of AC presence or absence.
    } else {
      on = off = 0; // Hysteresis preserves a previously established condition.
    }
  }
};

inline unsigned selfTest() {
  uint16_t values[200]; uint32_t times[200]; unsigned passed = 0;
  for (unsigned i = 0; i < 200; ++i) { times[i] = i * 1000; values[i] = 1650 + int(300 * sin(376.9911184307752 * i / 1000.0)); }
  Frame live = analyze(values, times, 200);
  passed += live.valid && live.rms > 209 && live.rms < 215 && live.coherence > .95;
  Detector detector; detector.update(live, false, 210); passed += !detector.known;
  detector.update(live, true, 210); detector.update(live, true, 210); passed += detector.known && detector.present;
  for (unsigned i = 0; i < 200; ++i) values[i] = 1650;
  Frame absent = analyze(values, times, 200); passed += absent.valid && absent.rms == 0;
  detector.update(absent, true, 210); passed += detector.known && detector.present;
  detector.update(absent, true, 210); passed += detector.known && !detector.present;
  for (unsigned i = 0; i < 200; ++i) values[i] = 0;
  Frame missing = analyze(values, times, 200); detector.update(missing, true, 210);
  passed += !missing.valid && !detector.known;
  for (unsigned i = 0; i < 200; ++i) values[i] = 1650 + int(300 * sin(314.1592653589793 * i / 1000.0));
  Frame hz50 = analyze(values, times, 200); passed += hz50.valid && hz50.coherence > .95;
  for (unsigned i = 0; i < 40; ++i) values[i] = 4095;
  passed += !analyze(values, times, 200).valid;
  passed += !analyze(values, times, 20).valid;
  return passed;
}
} // namespace PowerSignal
