-- 0009 conversations created before 0008 have no reflected_to; the sweep's
--      `message_count - reflected_to` then fails ("subtraction with 'int' and 'none'").
UPDATE conversation SET reflected_to = 0 WHERE reflected_to = NONE RETURN NONE;
