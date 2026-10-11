package com.mformusic.backend.service;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.util.SongText;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SearchRankerTest {

    static Song song(String id, String title, String artist, int duration) {
        Song s = new Song();
        s.setExternalTrackId(id);
        s.setTitle(title);
        s.setArtistName(artist);
        s.setDurationInSeconds(duration);
        return s;
    }

    static List<SearchRanker.Candidate> saavn(List<Song> songs) {
        List<SearchRanker.Candidate> out = new ArrayList<>();
        for (int i = 0; i < songs.size(); i++) out.add(new SearchRanker.Candidate(songs.get(i), i, songs.size(), false));
        return out;
    }

    @Test void htmlEntitiesAreDecodedIncludingDoubleEscaping() {
        assertEquals("Tum Hi Ho (From \"Aashiqui 2\")", SongText.unescape("Tum Hi Ho (From &quot;Aashiqui 2&quot;)"));
        assertEquals("Tum Hi Ho (From \"Aashiqui 2\")", SongText.unescape("Tum Hi Ho (From &amp;quot;Aashiqui 2&amp;quot;)"));
        assertNull(SongText.unescape(null));
        Song s = song("x", "A &amp; B", "C &amp; D", 1);
        s.unescapeText();
        assertEquals("A & B", s.getTitle());
        assertEquals("C & D", s.getArtistName());
    }

    @Test void exactSongBeyondSaavnTopFiveRanksFirst() {
        List<Song> songs = new ArrayList<>();
        for (int i = 0; i < 8; i++) songs.add(song("p" + i, "Tum Hi Ho Remix " + i, "DJ " + i, 200 + i));
        songs.add(song("want", "Tum Ho", "Jokhim", 240));
        songs.add(song("dup", "Tum Ho", "Jokhim", 241));
        List<Song> ranked = SearchRanker.rank("tum ho jokhim", saavn(songs), 30);
        assertEquals("want", ranked.get(0).getExternalTrackId());
        assertEquals(1, ranked.stream().filter(s -> s.getTitle().equals("Tum Ho")).count());
        assertEquals("want", SearchRanker.rank("tum ho", saavn(songs), 30).get(0).getExternalTrackId());
    }

    @Test void typoToleranceAndArtistMatch() {
        List<Song> songs = List.of(song("b", "Kesar", "Someone", 100), song("a", "Kesariya", "Arijit Singh", 268));
        assertEquals("a", SearchRanker.rank("kesariyaa arijit", saavn(songs), 5).get(0).getExternalTrackId());
    }

    @Test void localCachedRowWinsOverSameTrackFromSaavn() {
        Song local = song("same", "Raaz", "Zaeden", 200);
        local.setId(42L);
        List<SearchRanker.Candidate> c = new ArrayList<>();
        c.add(new SearchRanker.Candidate(local, 0, 1, true));
        c.add(new SearchRanker.Candidate(song("same", "Raaz", "Zaeden", 200), 0, 1, false));
        List<Song> ranked = SearchRanker.rank("raaz", c, 10);
        assertEquals(1, ranked.size());
        assertEquals(42L, ranked.get(0).getId());
    }
}
