package com.mformusic.backend.repository;

import com.mformusic.backend.model.LikedSong;
import com.mformusic.backend.model.Song;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;
import java.util.Optional;

public interface LikedSongRepository extends JpaRepository<LikedSong, Long> {

    Optional<LikedSong> findByUserIdAndSongId(Long userId, Long songId);

    boolean existsByUserIdAndSongId(Long userId, Long songId);

    @Query("SELECT l.song FROM LikedSong l WHERE l.user.id = :userId ORDER BY l.likedAt DESC")
    List<Song> findLikedSongsByUserId(@Param("userId") Long userId);
}
