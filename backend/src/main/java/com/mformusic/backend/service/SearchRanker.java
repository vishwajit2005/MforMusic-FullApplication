package com.mformusic.backend.service;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.util.SongText;

import java.util.*;

/**
 * Relevance ranking for song search (Spotify-style): the song whose title/artist
 * best matches what was typed comes first, regardless of whether it came from the
 * local cache or JioSaavn. JioSaavn's own order (roughly popularity) breaks ties.
 */
public final class SearchRanker {

    private SearchRanker() {}

    public record Candidate(Song song, int sourcePosition, int sourceSize, boolean local) {}

    public static List<Song> rank(String query, List<Candidate> candidates, int limit) {
        String q = SongText.normalize(query);
        List<String> qTokens = q.isEmpty() ? List.of() : List.of(q.split(" "));

        record Scored(Song song, double score, int order) {}
        List<Scored> scored = new ArrayList<>();
        int order = 0;
        for (Candidate c : candidates) {
            scored.add(new Scored(c.song(), score(q, qTokens, c), order++));
        }
        scored.sort(Comparator.comparingDouble(Scored::score).reversed().thenComparingInt(Scored::order));

        // Drop exact duplicates (same title + same artists + ~same length), keep distinct versions.
        List<Song> out = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();
        Set<String> seenKeys = new HashSet<>();
        for (Scored s : scored) {
            Song song = s.song();
            if (song.getExternalTrackId() == null || !seenIds.add(song.getExternalTrackId())) continue;
            int duration = song.getDurationInSeconds() == null ? -1 : song.getDurationInSeconds() / 5;
            String key = SongText.normalize(song.getTitle()) + "|" + new TreeSet<>(SongText.artists(song.getArtistName())) + "|" + duration;
            if (!seenKeys.add(key)) continue;
            out.add(song);
            if (out.size() >= limit) break;
        }
        return out;
    }

    static double score(String q, List<String> qTokens, Candidate c) {
        if (q.isEmpty()) return 0;
        String title = SongText.normalize(c.song().getTitle());
        String artist = SongText.normalize(c.song().getArtistName());
        String both = (title + " " + artist).trim();
        Set<String> words = new HashSet<>(Arrays.asList(both.split(" ")));

        double score = 0;
        if (title.equals(q)) score += 100;
        else if (title.startsWith(q)) score += 60;
        else if (title.contains(q)) score += 35;
        if (both.contains(q) || (artist + " " + title).contains(q)) score += 15;

        int matched = 0;
        for (String token : qTokens) {
            if (words.contains(token)) matched++;
            else if (token.length() >= 3 && words.stream().anyMatch(w -> w.startsWith(token))) matched++;
            else if (token.length() >= 4 && words.stream().anyMatch(w -> withinOneEdit(w, token))) matched++;
        }
        if (!qTokens.isEmpty()) {
            score += 40.0 * matched / qTokens.size();
            if (matched == qTokens.size()) score += 20;
        }
        for (String a : SongText.artists(c.song().getArtistName())) {
            if (q.contains(a)) { score += 12; break; }
        }
        // JioSaavn order as a gentle popularity prior; local cache gets a small familiarity bonus.
        if (c.sourceSize() > 0) score += 8.0 * (c.sourceSize() - c.sourcePosition()) / c.sourceSize();
        if (c.local()) score += 3;
        return score;
    }

    static boolean withinOneEdit(String a, String b) {
        int la = a.length(), lb = b.length();
        if (Math.abs(la - lb) > 1) return false;
        int i = 0, j = 0, edits = 0;
        while (i < la && j < lb) {
            if (a.charAt(i) == b.charAt(j)) { i++; j++; continue; }
            if (++edits > 1) return false;
            if (la > lb) i++;
            else if (lb > la) j++;
            else { i++; j++; }
        }
        return edits + (la - i) + (lb - j) <= 1;
    }
}
