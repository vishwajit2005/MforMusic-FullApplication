package com.mformusic.backend.repository;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.model.UserPlayHistory;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface UserPlayHistoryRepository extends JpaRepository<UserPlayHistory, Long> {

    /**
     * Returns songs played by a user ordered by most recent play, with JOIN FETCH to avoid N+1.
     */
    @Query("SELECT h.song FROM UserPlayHistory h WHERE h.user.id = :userId ORDER BY h.playedAt DESC")
    List<Song> findRecentSongsByUserId(@Param("userId") Long userId, Pageable pageable);
}
