#!/bin/bash

# Snapshot Cleanup Script
# Removes snapshot files older than 5 minutes and their corresponding database records
# Note: Thumbnails are not cleaned up here - they are deleted when parent files are deleted
# Author: Generated for ClippeX2 project

set -uo pipefail

# Configuration - with Docker-friendly dynamic paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOTS_DIR="${SNAPSHOTS_DIR:-${SCRIPT_DIR}/static/clips/snapshots}"
DATABASE_PATH="${DATABASE_PATH:-${SCRIPT_DIR}/static/db/database.db}"
LOG_FILE="${LOG_FILE:-${SCRIPT_DIR}/cleanup_snapshots.log}"
MINUTES_OLD="${CLEANUP_MINUTES:-5}"

# Function to log messages with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check if required tools are available
check_dependencies() {
    if ! command -v sqlite3 &> /dev/null; then
        log_message "ERROR: sqlite3 command not found. Please install sqlite3."
        exit 1
    fi
    
    if [[ ! -d "$SNAPSHOTS_DIR" ]]; then
        log_message "WARNING: Snapshots directory does not exist: $SNAPSHOTS_DIR"
        # Don't exit, just skip snapshots cleanup
    fi
    
    if [[ ! -f "$DATABASE_PATH" ]]; then
        log_message "WARNING: Database file does not exist: $DATABASE_PATH"
        # Don't exit, database operations will be skipped with errors logged
    fi
}

# Function to remove database record for a given file path
remove_from_database() {
    local file_path="$1"
    local result
    
    # Remove the record from snapshots table
    if [[ ! -f "$DATABASE_PATH" ]]; then
        log_message "Database file does not exist, skipping database cleanup for: $file_path"
        return 0
    fi
    
    result=$(sqlite3 "$DATABASE_PATH" "DELETE FROM snapshots WHERE file_path = '$file_path'; SELECT changes();" 2>/dev/null || echo "0")
    
    if [[ "$result" -gt 0 ]]; then
        log_message "Removed database record for: $file_path"
        return 1  # Return 1 to indicate record was deleted
    else
        log_message "No database record found for: $file_path"
        return 0  # Return 0 to indicate no record found (but not an error)
    fi
}

# Function to cleanup old snapshot files
cleanup_snapshots() {
    local files_deleted=0
    local db_records_deleted=0
    
    log_message "Starting snapshot cleanup - removing files older than $MINUTES_OLD minutes"
    
    # Check if snapshots directory exists before processing
    if [[ ! -d "$SNAPSHOTS_DIR" ]]; then
        log_message "Skipping snapshot cleanup - directory does not exist: $SNAPSHOTS_DIR"
        return 0
    fi
    
    # Find files older than specified minutes and process them
    while IFS= read -r -d '' file; do
        [[ -z "$file" ]] && continue
        
        # Get the absolute path for database lookup
        abs_file_path=$(realpath "$file")
        
        log_message "Processing file: $file"
        
        # Try to remove from database first
        if remove_from_database "$abs_file_path"; then
            # Return value 0 means no record found - don't increment counter
            true
        else
            # Return value 1 means record was deleted - increment counter
            ((db_records_deleted++))
        fi
        
        # Remove the physical file
        if rm -f "$file"; then
            log_message "Deleted file: $file"
            ((files_deleted++))
        else
            log_message "ERROR: Failed to delete file: $file"
        fi
    done < <(find "$SNAPSHOTS_DIR" -type f \( -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) -mmin +$MINUTES_OLD -print0 2>/dev/null)
    
    log_message "Cleanup completed - Files deleted: $files_deleted, DB records deleted: $db_records_deleted"
}


# Function to handle script interruption
cleanup_on_exit() {
    log_message "Script interrupted or completed"
}

# Main execution
main() {
    # Set up signal handlers
    trap cleanup_on_exit EXIT INT TERM
    
    log_message "=== Snapshot Cleanup Script Started ==="
    
    # Check dependencies
    check_dependencies
    
    # Perform cleanup
    cleanup_snapshots
    
    log_message "=== Snapshot Cleanup Script Completed ==="
}

# Run main function
main "$@"