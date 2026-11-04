package br.com.climaguard.app;

/** Pure Java freshness/sequence tracking; elapsed time must be monotonic. */
public final class ReadingState {
    private String boot = "";
    private long sequence = 0;
    private long sampleAt = Long.MIN_VALUE;
    private long contactAt = Long.MIN_VALUE;

    public boolean accept(String nextBoot, long nextSequence, long sampleAgeMs, long now) {
        if (nextBoot == null || !nextBoot.matches("[0-9a-f]{16}") || nextSequence < 1 || sampleAgeMs < 0 || sampleAgeMs >= 15000)
            throw new IllegalArgumentException("Leitura inválida");
        contactAt = now;
        if (boot.equals(nextBoot) && nextSequence <= sequence) return false;
        boot = nextBoot;
        sequence = nextSequence;
        sampleAt = now - sampleAgeMs;
        return true;
    }

    public boolean online(long now) {
        return sampleAt != Long.MIN_VALUE && contactAt != Long.MIN_VALUE
            && now - sampleAt < 8000 && now - contactAt < 2500;
    }

    public long age(long now) { return sampleAt == Long.MIN_VALUE ? -1 : Math.max(0, now - sampleAt); }
}
