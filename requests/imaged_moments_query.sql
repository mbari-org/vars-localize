SELECT DISTINCT
                imaged_moment_uuid, image_url
FROM
     M3_ANNOTATIONS.dbo.annotations
WHERE
      concept = '{0}' AND
      image_format = 'image/png'
ORDER BY
         imaged_moment_uuid
OFFSET {1} ROWS
FETCH FIRST {2} ROWS ONLY