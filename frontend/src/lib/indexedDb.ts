/**
 * IndexedDB Cache Layer for Code Standards
 * 
 * This module provides:
 * - Local caching of high-frequency code_standard items
 * - Incremental sync with server
 * - Fast local lookups for IDE pre-review
 * 
 * Database Structure:
 * - code_standards: Main store for knowledge items
 * - sync_metadata: Tracks sync timestamps per repository
 * - access_log: Tracks access frequency for cache optimization
 */

const DB_NAME = "EchoReview_Cache";
const DB_VERSION = 1;

const STORES = {
  CODE_STANDARDS: "code_standards",
  SYNC_METADATA: "sync_metadata",
  ACCESS_LOG: "access_log",
};

export interface CachedKnowledgeItem {
  id: number;
  repo_id: number;
  knowledge_type: string;
  title: string;
  content: string;
  examples?: string[];
  tags?: string[];
  file_patterns?: string[];
  confidence_score: number;
  occurrence_count: number;
  source_pr_ids?: number[];
  created_at: string;
  updated_at: string;
  synced_at: string;
}

export interface SyncMetadata {
  repo_id: number;
  last_sync_at: string;
  item_count: number;
  last_accessed_at: string;
}

export interface AccessLog {
  id?: number;
  item_id: number;
  repo_id: number;
  accessed_at: string;
  context: string;
}

let dbInstance: IDBDatabase | null = null;

export async function openDatabase(): Promise<IDBDatabase> {
  if (dbInstance) return dbInstance;

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      dbInstance = request.result;
      resolve(dbInstance);
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      if (!db.objectStoreNames.contains(STORES.CODE_STANDARDS)) {
        const standardsStore = db.createObjectStore(STORES.CODE_STANDARDS, {
          keyPath: "id",
        });
        standardsStore.createIndex("repo_id", "repo_id", { unique: false });
        standardsStore.createIndex(
          "repo_knowledge_type",
          ["repo_id", "knowledge_type"],
          { unique: false }
        );
        standardsStore.createIndex("occurrence_count", "occurrence_count", {
          unique: false,
        });
      }

      if (!db.objectStoreNames.contains(STORES.SYNC_METADATA)) {
        db.createObjectStore(STORES.SYNC_METADATA, { keyPath: "repo_id" });
      }

      if (!db.objectStoreNames.contains(STORES.ACCESS_LOG)) {
        const accessStore = db.createObjectStore(STORES.ACCESS_LOG, {
          keyPath: "id",
          autoIncrement: true,
        });
        accessStore.createIndex("item_id", "item_id", { unique: false });
        accessStore.createIndex("repo_id", "repo_id", { unique: false });
      }
    };
  });
}

export async function closeDatabase(): Promise<void> {
  if (dbInstance) {
    dbInstance.close();
    dbInstance = null;
  }
}

export async function saveCodeStandards(
  repoId: number,
  items: CachedKnowledgeItem[]
): Promise<void> {
  const db = await openDatabase();
  const now = new Date().toISOString();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(
      [STORES.CODE_STANDARDS, STORES.SYNC_METADATA],
      "readwrite"
    );

    const standardsStore = transaction.objectStore(STORES.CODE_STANDARDS);
    const metadataStore = transaction.objectStore(STORES.SYNC_METADATA);

    items.forEach((item) => {
      const cachedItem: CachedKnowledgeItem = {
        ...item,
        repo_id: repoId,
        synced_at: now,
      };
      standardsStore.put(cachedItem);
    });

    const metadata: SyncMetadata = {
      repo_id: repoId,
      last_sync_at: now,
      item_count: items.length,
      last_accessed_at: now,
    };
    metadataStore.put(metadata);

    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

export async function getCodeStandards(
  repoId: number,
  knowledgeType?: string
): Promise<CachedKnowledgeItem[]> {
  const db = await openDatabase();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(
      [STORES.CODE_STANDARDS, STORES.SYNC_METADATA],
      "readonly"
    );

    const standardsStore = transaction.objectStore(STORES.CODE_STANDARDS);
    const metadataStore = transaction.objectStore(STORES.SYNC_METADATA);

    let request: IDBRequest;

    if (knowledgeType) {
      const index = standardsStore.index("repo_knowledge_type");
      request = index.getAll(IDBKeyRange.bound(
        [repoId, knowledgeType],
        [repoId, knowledgeType]
      ));
    } else {
      const index = standardsStore.index("repo_id");
      request = index.getAll(repoId);
    }

    request.onsuccess = () => {
      const items: CachedKnowledgeItem[] = request.result;

      items.sort((a, b) => {
        const scoreA = a.confidence_score * a.occurrence_count;
        const scoreB = b.confidence_score * b.occurrence_count;
        return scoreB - scoreA;
      });

      const metadataRequest = metadataStore.get(repoId);
      metadataRequest.onsuccess = () => {
        const metadata = metadataRequest.result as SyncMetadata | undefined;
        if (metadata) {
          metadata.last_accessed_at = new Date().toISOString();
          const writeTx = db.transaction(STORES.SYNC_METADATA, "readwrite");
          writeTx.objectStore(STORES.SYNC_METADATA).put(metadata);
        }
      };

      resolve(items);
    };

    request.onerror = () => reject(request.error);
  });
}

export async function getHighFrequencyStandards(
  repoId: number,
  limit: number = 20
): Promise<CachedKnowledgeItem[]> {
  const db = await openDatabase();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.CODE_STANDARDS, "readonly");
    const store = transaction.objectStore(STORES.CODE_STANDARDS);
    const index = store.index("occurrence_count");

    const request = index.openCursor(null, "prev");
    const items: CachedKnowledgeItem[] = [];

    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor && items.length < limit) {
        if (cursor.value.repo_id === repoId) {
          items.push(cursor.value as CachedKnowledgeItem);
        }
        cursor.continue();
      } else {
        resolve(items);
      }
    };

    request.onerror = () => reject(request.error);
  });
}

export async function getSyncMetadata(repoId: number): Promise<SyncMetadata | null> {
  const db = await openDatabase();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SYNC_METADATA, "readonly");
    const store = transaction.objectStore(STORES.SYNC_METADATA);
    const request = store.get(repoId);

    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

export async function logAccess(
  itemId: number,
  repoId: number,
  context: string = "pre_review"
): Promise<void> {
  const db = await openDatabase();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.ACCESS_LOG, "readwrite");
    const store = transaction.objectStore(STORES.ACCESS_LOG);

    const log: AccessLog = {
      item_id: itemId,
      repo_id: repoId,
      accessed_at: new Date().toISOString(),
      context,
    };

    store.add(log);

    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

export async function clearOldAccessLogs(
  olderThanDays: number = 30
): Promise<void> {
  const db = await openDatabase();
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - olderThanDays);

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.ACCESS_LOG, "readwrite");
    const store = transaction.objectStore(STORES.ACCESS_LOG);
    const request = store.openCursor();

    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor) {
        const accessedAt = new Date((cursor.value as AccessLog).accessed_at);
        if (accessedAt < cutoffDate) {
          cursor.delete();
        }
        cursor.continue();
      } else {
        resolve();
      }
    };

    request.onerror = () => reject(request.error);
  });
}

export async function clearRepositoryCache(repoId: number): Promise<void> {
  const db = await openDatabase();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(
      [STORES.CODE_STANDARDS, STORES.SYNC_METADATA, STORES.ACCESS_LOG],
      "readwrite"
    );

    const standardsStore = transaction.objectStore(STORES.CODE_STANDARDS);
    const standardsIndex = standardsStore.index("repo_id");
    const standardsCursor = standardsIndex.openCursor(repoId);

    standardsCursor.onsuccess = () => {
      const cursor = standardsCursor.result;
      if (cursor) {
        cursor.delete();
        cursor.continue();
      }
    };

    const metadataStore = transaction.objectStore(STORES.SYNC_METADATA);
    metadataStore.delete(repoId);

    const accessStore = transaction.objectStore(STORES.ACCESS_LOG);
    const accessIndex = accessStore.index("repo_id");
    const accessCursor = accessIndex.openCursor(repoId);

    accessCursor.onsuccess = () => {
      const cursor = accessCursor.result;
      if (cursor) {
        cursor.delete();
        cursor.continue();
      }
    };

    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

export async function getCacheStats(repoId: number): Promise<{
  itemCount: number;
  lastSyncAt: string | null;
  lastAccessedAt: string | null;
}> {
  const metadata = await getSyncMetadata(repoId);
  const standards = await getCodeStandards(repoId);

  return {
    itemCount: standards.length,
    lastSyncAt: metadata?.last_sync_at || null,
    lastAccessedAt: metadata?.last_accessed_at || null,
  };
}

export function isIndexedDBSupported(): boolean {
  return "indexedDB" in window;
}
