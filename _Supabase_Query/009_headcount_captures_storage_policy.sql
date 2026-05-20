-- Allow the anon role to upload images to the headcount-captures bucket.
-- The RPi uses the anon key, so without this policy all uploads return 403.

CREATE POLICY "anon_insert_headcount_captures"
ON storage.objects FOR INSERT
TO anon
WITH CHECK (bucket_id = 'headcount-captures');

-- Needed for upsert=true (the upload call sets this flag).
CREATE POLICY "anon_update_headcount_captures"
ON storage.objects FOR UPDATE
TO anon
USING (bucket_id = 'headcount-captures');
