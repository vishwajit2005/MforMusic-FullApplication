package com.mformusic.backend.util;

import org.springframework.web.util.HtmlUtils;

import java.text.Normalizer;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/** Text helpers for song titles/artists coming from JioSaavn. */
public final class SongText {

    private static final Pattern NON_WORD = Pattern.compile("[^\\p{L}\\p{N} ]+");
    private static final Pattern SPACES = Pattern.compile("\\s+");
    private static final Pattern ARTIST_SPLIT =
            Pattern.compile("\\s*(?:,|&|/|;|\\bx\\b|\\band\\b|\\bfeat\\.?|\\bft\\.?|\\bfeaturing\\b)\\s*");

    private SongText() {}

    /** "Tum Hi Ho (From &quot;Aashiqui 2&quot;)" -> "Tum Hi Ho (From "Aashiqui 2")". Handles double-escaping. */
    public static String unescape(String text) {
        if (text == null || text.indexOf('&') < 0) return text;
        String out = text;
        for (int i = 0; i < 3 && out.indexOf('&') >= 0; i++) {
            String next = HtmlUtils.htmlUnescape(out);
            if (next.equals(out)) break;
            out = next;
        }
        return out;
    }

    /** Lower-case, accents/punctuation removed, single-spaced. */
    public static String normalize(String text) {
        if (text == null) return "";
        String s = Normalizer.normalize(unescape(text), Normalizer.Form.NFKD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT);
        s = NON_WORD.matcher(s).replaceAll(" ");
        return SPACES.matcher(s).replaceAll(" ").trim();
    }

    public static Set<String> artists(String artists) {
        if (artists == null || artists.isBlank()) return Set.of();
        return Arrays.stream(ARTIST_SPLIT.split(unescape(artists).toLowerCase(Locale.ROOT)))
                .map(SongText::normalize)
                .filter(a -> !a.isEmpty() && !a.equals("unknown artist"))
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }
}
