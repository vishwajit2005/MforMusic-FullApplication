package com.mformusic.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;

@EnableAsync
@SpringBootApplication
public class BackendApplication {

	public static void main(String[] args) {
		loadDotEnv();
		SpringApplication.run(BackendApplication.class, args);
	}

	private static void loadDotEnv() {
		String[] possiblePaths = {".env", "backend/.env", "../backend/.env"};
		for (String path : possiblePaths) {
			File envFile = new File(path);
			if (envFile.exists() && envFile.isFile()) {
				try {
					List<String> lines = Files.readAllLines(Paths.get(path));
					for (String line : lines) {
						String trimmed = line.trim();
						if (trimmed.isEmpty() || trimmed.startsWith("#")) {
							continue;
						}
						int eqIdx = trimmed.indexOf('=');
						if (eqIdx > 0) {
							String key = trimmed.substring(0, eqIdx).trim();
							String val = trimmed.substring(eqIdx + 1).trim();
							// Only set if not already provided by OS environment or existing system property
							if (System.getenv(key) == null && System.getProperty(key) == null) {
								System.setProperty(key, val);
							}
						}
					}
					break;
				} catch (Exception ignored) {
				}
			}
		}
	}
}