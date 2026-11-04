package br.com.climaguard.app;

/** Strict IPv4 parsing; never accepts hostnames, URL paths or public destinations. */
public final class LanAddress {
    public static long parse(String text) {
        if (text == null || !text.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}"))
            throw new IllegalArgumentException("Digite somente o IP, como 192.168.1.13.");
        long result = 0;
        for (String part : text.split("\\.")) {
            int value = Integer.parseInt(part);
            if (value > 255 || (part.length() > 1 && part.startsWith("0")))
                throw new IllegalArgumentException("IP inválido.");
            result = (result << 8) | value;
        }
        boolean privateIp = (result >>> 24) == 10 || (result >>> 20) == 0xac1 || (result >>> 16) == 0xc0a8;
        if (!privateIp) throw new IllegalArgumentException("Use o IP local da placa.");
        return result;
    }

    public static boolean onLink(long address, long local, int prefix) {
        if (prefix < 1 || prefix > 30) return false;
        long mask = (0xffffffffL << (32 - prefix)) & 0xffffffffL;
        long network = local & mask, broadcast = network | (~mask & 0xffffffffL);
        return (address & mask) == network && address != network && address != broadcast && address != local;
    }

    public static String format(long address) {
        return ((address >>> 24) & 255) + "." + ((address >>> 16) & 255) + "." + ((address >>> 8) & 255) + "." + (address & 255);
    }
}
